"""Yahoo Finance Key Statistics scraper.

Public surface: `fetch(ticker)` returns a `StockMetrics` (possibly partial)
or `None` on hard failure.
"""
from __future__ import annotations

from collections.abc import Callable

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


# Label-to-field dispatch maps for the flat statistics sections on Yahoo's
# Key Statistics page. The exact label strings must match what the rendered
# page produces — Yahoo embeds double spaces before parenthetical qualifiers
# like "(ttm)"/"(mrq)"/"(yoy)" and appends bare footnote digits (e.g. the
# "4" in "Payout Ratio4") directly to the label text, with no separator.
_Converter = Callable[[str | None], float | None]


_PROFITABILITY_MAP: dict[str, tuple[str, _Converter]] = {
    "Profit Margin": ("profit_margin", _to_percent),
    "Operating Margin  (ttm)": ("operating_margin", _to_percent),
}

_MANAGEMENT_MAP: dict[str, tuple[str, _Converter]] = {
    "Return on Assets  (ttm)": ("roa", _to_percent),
    "Return on Equity  (ttm)": ("roe", _to_percent),
}

_INCOME_MAP: dict[str, tuple[str, _Converter]] = {
    "Quarterly Revenue Growth  (yoy)": ("revenue_growth_yoy", _to_percent),
    "Quarterly Earnings Growth  (yoy)": ("earnings_growth_yoy", _to_percent),
}

_BALANCE_SHEET_MAP: dict[str, tuple[str, _Converter]] = {
    "Total Cash  (mrq)": ("total_cash", _to_magnitude),
    "Total Debt  (mrq)": ("total_debt", _to_magnitude),
    "Total Debt/Equity  (mrq)": ("debt_to_equity", _to_percent),
    "Current Ratio  (mrq)": ("current_ratio", _to_float),
}

_CASHFLOW_MAP: dict[str, tuple[str, _Converter]] = {
    "Operating Cash Flow  (ttm)": ("operating_cash_flow", _to_magnitude),
    "Levered Free Cash Flow  (ttm)": ("levered_free_cash_flow", _to_magnitude),
}

_PRICE_HISTORY_MAP: dict[str, tuple[str, _Converter]] = {
    "Beta (5Y Monthly)": ("beta", _to_float),
}

_DIVIDEND_MAP: dict[str, tuple[str, _Converter]] = {
    # Yahoo appends footnote digits directly to dividend labels (no space).
    "Forward Annual Dividend Yield4": ("forward_dividend_yield", _to_percent),
    "Payout Ratio4": ("payout_ratio", _to_percent),
}

_ALL_FLAT_MAPS: list[dict[str, tuple[str, _Converter]]] = [
    _PROFITABILITY_MAP,
    _MANAGEMENT_MAP,
    _INCOME_MAP,
    _BALANCE_SHEET_MAP,
    _CASHFLOW_MAP,
    _PRICE_HISTORY_MAP,
    _DIVIDEND_MAP,
]


def _parse_stat_rows(doc: HTMLParser) -> dict[str, str]:
    """Walk the document and return {label: raw_value_string} for every
    recognizable 2-cell row.

    Yahoo's Key Statistics page renders each flat section as a
    ``<table class="table yf-vaowmx">`` whose body contains ``<tr>`` rows
    with exactly two ``<td>`` cells: a ``label`` cell and a ``value`` cell.
    We rely on that shape universally: any ``<tr>`` with two ``<td>``
    children is treated as a label/value pair. First occurrence wins so
    that the flat-table parser isn't polluted by duplicate labels that
    might appear in the Valuation Measures historical grid.
    """
    rows: dict[str, str] = {}
    for tr in doc.css("tr"):
        cells = tr.css("td")
        if len(cells) != 2:
            continue
        label = cells[0].text(strip=True)
        value = cells[1].text(strip=True)
        if label and label not in rows:
            rows[label] = value
    return rows


def _apply_flat_maps(rows: dict[str, str]) -> dict[str, float | None]:
    """Route parsed label/value rows into StockMetrics field values via
    per-section dispatch dicts. Unrecognized labels are ignored."""
    out: dict[str, float | None] = {}
    for label_map in _ALL_FLAT_MAPS:
        for label, (field, converter) in label_map.items():
            if label in rows:
                out[field] = converter(rows[label])
    return out


def _parse_document(html: str, ticker: str) -> StockMetrics | None:
    """Parse a Yahoo Key Statistics HTML page into a StockMetrics.

    Returns None on hard parse failure (root element missing). Otherwise
    returns a (possibly partial) StockMetrics populated from the flat
    statistics sections (Profitability, Management Effectiveness, Income
    Statement, Balance Sheet, Cash Flow, Stock Price History, and
    Dividends & Splits). The Valuation Measures historical grid is parsed
    separately in a later task.
    """
    try:
        doc = HTMLParser(html)
    except Exception:
        return None
    if doc.body is None:
        return None

    rows = _parse_stat_rows(doc)
    flat_fields = _apply_flat_maps(rows)

    return StockMetrics(ticker=ticker, **flat_fields)
