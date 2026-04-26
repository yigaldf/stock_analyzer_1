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


def validate_tickers(tickers: list[str]) -> list[str]:
    """Return only the tickers that yfinance recognizes. Runs in parallel."""

    def _check(t: str) -> str | None:
        try:
            info = yf.Ticker(t).info
            return t if _is_valid_info(info) else None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(_check, tickers))

    return [t for t in results if t is not None]


def get_stock_info(ticker: str) -> StockInfo | None:
    """Fetch basic info for one ticker."""
    try:
        info = yf.Ticker(ticker).info
    except Exception:
        return None
    if not _is_valid_info(info):
        return None

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
