from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import yfinance as yf

from app.models.schemas import StockInfo, StockMetrics
from app.services import metrics_cache, yahoo_scraper


def _is_valid_info(info: dict | None) -> bool:
    """A ticker is valid if yfinance returns a dict with a longName or shortName."""
    if not info:
        return False
    return bool(info.get("longName") or info.get("shortName"))


def _yfinance_info(ticker: str) -> dict | None:
    """Fetch yfinance ``.info``, swallowing any error into None."""
    try:
        return yf.Ticker(ticker).info
    except Exception:
        return None


def _scraper_validates(ticker: str) -> bool:
    """Fallback existence-check via the Yahoo scraper, used when yfinance is
    blocked (e.g. on cloud IPs like Hugging Face). A non-None fetch means the
    scraper extracted real data, so the ticker is real."""
    try:
        return yahoo_scraper.fetch(ticker) is not None
    except Exception:
        return False


def validate_tickers(tickers: list[str]) -> list[str]:
    """Return only the tickers that are recognized. Runs in parallel.

    yfinance is the fast primary; when it returns nothing (blocked), each
    ticker falls back to the Yahoo scraper."""

    def _check(t: str) -> str | None:
        if _is_valid_info(_yfinance_info(t)):
            return t
        return t if _scraper_validates(t) else None

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(_check, tickers))

    return [t for t in results if t is not None]


def get_stock_info(ticker: str) -> StockInfo | None:
    """Fetch basic info for one ticker.

    yfinance is the fast primary. When it's blocked (cloud IPs), we fall back
    to the Yahoo scraper, which yields the company name and market cap but not
    sector or live price — those degrade to "Unknown"/0.0."""
    info = _yfinance_info(ticker)
    if _is_valid_info(info):
        name = info.get("longName") or info.get("shortName") or ticker
        sector = info.get("sector") or "Unknown"
        price = info.get("currentPrice") or info.get("regularMarketPrice") or 0.0
        mcap = info.get("marketCap")
        market_cap = float(mcap) if mcap is not None else None
        return StockInfo(
            ticker=ticker,
            name=name,
            sector=sector,
            current_price=float(price),
            market_cap=market_cap,
        )

    metrics = yahoo_scraper.fetch(ticker)
    if metrics is None:
        return None
    return StockInfo(
        ticker=ticker,
        name=metrics.name or ticker,
        sector="Unknown",
        current_price=0.0,
        market_cap=metrics.market_cap,
    )


def get_stock_metrics(ticker: str) -> StockMetrics | None:
    """Fetch all scoring metrics for one ticker via the Yahoo HTML scraper.

    Step 1 (`validate_tickers`, `get_stock_info`) still uses yfinance because
    it's faster for the existence-check and basic info use case. Step 3's
    full metrics fetch uses the scraper (via tiered httpx → Playwright
    pipeline) to get reliable PEG, historical valuation, same-snapshot
    pricing across peers, and source provenance.
    """
    cached = metrics_cache.get(ticker)
    if cached is not None:
        return cached

    metrics = yahoo_scraper.fetch(ticker)
    if metrics is not None:
        if metrics.name is None:
            try:
                info = yf.Ticker(ticker).info
                metrics.name = info.get("longName") or info.get("shortName")
            except Exception:
                pass
        metrics_cache.set(ticker, metrics)
    return metrics
