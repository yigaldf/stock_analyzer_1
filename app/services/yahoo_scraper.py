"""Yahoo Finance Key Statistics scraper.

Public surface: `fetch(ticker)` returns a `StockMetrics` (possibly partial)
or `None` on hard failure.
"""
from __future__ import annotations

from selectolax.parser import HTMLParser

from app.models.schemas import StockMetrics


def _to_float(s: str | None) -> float | None:
    """Parse a plain decimal string. Handles thousands separators and `--`."""
    if s is None:
        return None
    cleaned = s.strip().replace(",", "")
    if not cleaned or cleaned == "--":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _to_percent(s: str | None) -> float | None:
    """Parse `14.22%` or `-21.60%` -> 0.1422 / -0.216. `--` -> None."""
    if s is None:
        return None
    cleaned = s.strip().replace(",", "").rstrip("%")
    if not cleaned or cleaned == "--":
        return None
    try:
        return float(cleaned) / 100.0
    except ValueError:
        return None


_MAGNITUDE_SUFFIXES = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def _to_magnitude(s: str | None) -> float | None:
    """Parse `1.81B`, `824.08M`, `350K`, `123` -> raw float dollars. `--` -> None."""
    if s is None:
        return None
    cleaned = s.strip().replace(",", "")
    if not cleaned or cleaned == "--":
        return None
    multiplier = 1.0
    last = cleaned[-1].upper()
    if last in _MAGNITUDE_SUFFIXES:
        multiplier = _MAGNITUDE_SUFFIXES[last]
        cleaned = cleaned[:-1]
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return None


def _parse_document(html: str, ticker: str) -> StockMetrics | None:
    """Parse a Yahoo Key Statistics HTML page into a StockMetrics.

    Returns None on hard parse failure (root element missing).
    Returns a partial StockMetrics with None-filled fields when individual
    sections are missing. Real field parsing is added in later tasks — this
    scaffold only verifies the document is parseable and returns the ticker.
    """
    try:
        doc = HTMLParser(html)
    except Exception:
        return None
    if doc.body is None:
        return None
    return StockMetrics(ticker=ticker)
