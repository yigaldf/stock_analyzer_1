"""Tests for the tiered Yahoo Key Statistics fetcher.

The httpx primary path is tested with pytest-httpx mocks.
The Playwright fallback path is tested by monkeypatching
`_fetch_via_playwright` with a lambda that returns a canned HTML string,
so tests never launch a real Chromium browser.
"""

from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.services import yahoo_scraper
from app.services.yahoo_scraper import _URL_TEMPLATE, fetch

FIXTURE = (Path(__file__).parent / "fixtures" / "lulu_key_statistics.html").read_text()

# Yahoo's anti-bot 404 stub — minimal but recognizable. In practice the stub
# is ~502 bytes and contains the phrase "Content is currently unavailable";
# our stub detector checks both for small payload and the phrase.
ANTI_BOT_STUB = (
    "<html><meta charset='utf-8'>"
    "<script>"
    "document.write('<p>Content is currently unavailable.</p>"
    '<img src="//geo.yahoo.com/p?err=404" width="0px" height="0px"/>\');'
    "</script></html>"
)


def test_fetch_happy_path_returns_metrics_and_tags_httpx(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=_URL_TEMPLATE.format(ticker="LULU"),
        text=FIXTURE,
        status_code=200,
    )
    metrics = fetch("LULU")
    assert metrics is not None
    assert metrics.ticker == "LULU"
    assert metrics.source == "httpx"
    assert metrics.peg_ratio is not None
    assert len(metrics.valuation_history) >= 2


def test_fetch_falls_back_to_playwright_on_500(httpx_mock: HTTPXMock, monkeypatch):
    httpx_mock.add_response(
        url=_URL_TEMPLATE.format(ticker="LULU"),
        status_code=500,
    )
    monkeypatch.setattr(yahoo_scraper, "_fetch_via_playwright", lambda ticker: FIXTURE)
    metrics = fetch("LULU")
    assert metrics is not None
    assert metrics.source == "playwright"
    assert metrics.peg_ratio is not None


def test_fetch_falls_back_to_playwright_on_anti_bot_stub(
    httpx_mock: HTTPXMock, monkeypatch
):
    httpx_mock.add_response(
        url=_URL_TEMPLATE.format(ticker="LULU"),
        text=ANTI_BOT_STUB,
        status_code=200,
    )
    monkeypatch.setattr(yahoo_scraper, "_fetch_via_playwright", lambda ticker: FIXTURE)
    metrics = fetch("LULU")
    assert metrics is not None
    assert metrics.source == "playwright"


def test_fetch_falls_back_to_playwright_on_httpx_network_error(
    httpx_mock: HTTPXMock, monkeypatch
):
    httpx_mock.add_exception(httpx.ConnectError("no route"))
    monkeypatch.setattr(yahoo_scraper, "_fetch_via_playwright", lambda ticker: FIXTURE)
    metrics = fetch("LULU")
    assert metrics is not None
    assert metrics.source == "playwright"


def test_fetch_returns_none_when_both_backends_fail(httpx_mock: HTTPXMock, monkeypatch):
    httpx_mock.add_response(
        url=_URL_TEMPLATE.format(ticker="LULU"),
        status_code=500,
    )
    monkeypatch.setattr(yahoo_scraper, "_fetch_via_playwright", lambda ticker: None)
    assert fetch("LULU") is None


def test_fetch_propagates_when_playwright_raises_unguarded(
    httpx_mock: HTTPXMock, monkeypatch
):
    """If _fetch_via_playwright raises (not a wrapped PlaywrightError),
    fetch() propagates. The internal Exception catch inside
    _fetch_via_playwright is the single safety net; fetch() trusts it."""
    httpx_mock.add_exception(httpx.ReadTimeout("timeout"))

    def raising_playwright(ticker):
        raise RuntimeError("chromium crashed")

    monkeypatch.setattr(yahoo_scraper, "_fetch_via_playwright", raising_playwright)
    with pytest.raises(RuntimeError, match="chromium crashed"):
        fetch("LULU")


def test_fetch_falls_back_when_httpx_html_has_no_signal_fields(
    httpx_mock: HTTPXMock, monkeypatch
):
    """If httpx returns a 200 with parseable HTML but the parser
    extracts zero signal fields (e.g. a Yahoo skeleton shell that
    rendered before JS populated content), fetch() should treat it as
    a parse failure and fall back to Playwright rather than returning
    an all-None StockMetrics tagged source='httpx'."""
    empty_page = "<html><body><div>Loading...</div></body></html>"
    httpx_mock.add_response(
        url=_URL_TEMPLATE.format(ticker="LULU"),
        text=empty_page * 200,  # bloat above stub size threshold
        status_code=200,
    )
    monkeypatch.setattr(yahoo_scraper, "_fetch_via_playwright", lambda ticker: FIXTURE)
    metrics = fetch("LULU")
    assert metrics is not None
    assert metrics.source == "playwright"
    assert metrics.peg_ratio is not None


def test_fetch_returns_none_when_both_backends_return_empty_html(
    httpx_mock: HTTPXMock, monkeypatch
):
    """Defense in depth: if httpx AND Playwright both return HTML
    that parses to zero signal fields, fetch() returns None so the UI
    shows 'Couldn't fetch metrics' rather than a row of dashes with a
    misleading source badge."""
    empty_page = "<html><body><div>Loading...</div></body></html>"
    httpx_mock.add_response(
        url=_URL_TEMPLATE.format(ticker="LULU"),
        text=empty_page * 200,
        status_code=200,
    )
    monkeypatch.setattr(
        yahoo_scraper, "_fetch_via_playwright", lambda ticker: empty_page
    )
    assert fetch("LULU") is None
