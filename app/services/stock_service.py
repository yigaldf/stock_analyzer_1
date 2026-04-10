from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import yfinance as yf

from app.models.schemas import StockInfo, StockMetrics


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
    """Fetch all 12 scoring metrics + market_cap for one ticker."""
    try:
        info = yf.Ticker(ticker).info
    except Exception:
        return None
    if not _is_valid_info(info):
        return None

    def _get(key: str) -> float | None:
        v = info.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return StockMetrics(
        ticker=ticker,
        forward_pe=_get("forwardPE"),
        trailing_pe=_get("trailingPE"),
        peg_ratio=_get("pegRatio"),
        price_to_sales=_get("priceToSalesTrailing12Months"),
        market_cap=_get("marketCap"),
        profit_margin=_get("profitMargins"),
        operating_margin=_get("operatingMargins"),
        revenue_growth=_get("revenueGrowth"),
        eps_growth=_get("earningsGrowth"),
        roe=_get("returnOnEquity"),
        debt_to_equity=(
            _get("debtToEquity") / 100 if _get("debtToEquity") is not None else None
        ),
        beta=_get("beta"),
        dividend_yield=_get("dividendYield"),
    )
