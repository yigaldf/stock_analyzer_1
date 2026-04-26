"""Persistent disk cache for StockMetrics with a 12-hour TTL."""

from __future__ import annotations

from pathlib import Path

from diskcache import Cache

from app.models.schemas import StockMetrics

_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "metrics"
_TTL_SECONDS = 12 * 60 * 60  # 12 hours

_cache: Cache | None = None


def _get_cache() -> Cache:
    global _cache
    if _cache is None:
        _cache = Cache(str(_CACHE_DIR))
    return _cache


def get(ticker: str) -> StockMetrics | None:
    """Return cached metrics for *ticker*, or None if missing/expired."""
    return _get_cache().get(ticker)


def set(ticker: str, metrics: StockMetrics) -> None:
    """Store metrics for *ticker* with a 12-hour TTL."""
    _get_cache().set(ticker, metrics, expire=_TTL_SECONDS)
