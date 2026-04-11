from pathlib import Path

import pytest

from app.services.yahoo_scraper import _parse_document

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "lulu_key_statistics.html"


@pytest.fixture
def lulu_html() -> str:
    return FIXTURE_PATH.read_text()


def test_parse_document_returns_metrics_with_ticker(lulu_html):
    metrics = _parse_document(lulu_html, "LULU")
    assert metrics is not None
    assert metrics.ticker == "LULU"
