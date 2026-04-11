"""Yahoo Finance Key Statistics scraper.

Public surface: `fetch(ticker)` returns a `StockMetrics` (possibly partial)
or `None` on hard failure.
"""
from __future__ import annotations

from collections.abc import Callable

from selectolax.parser import HTMLParser

from app.models.schemas import QuarterlyValuation, StockMetrics


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


# Maps Yahoo valuation-grid row labels to (shared field name, converter).
# The StockMetrics snapshot field and QuarterlyValuation attribute happen
# to have the same name for every row, so we store a single name. Label
# strings must match the fixture verbatim — Yahoo does NOT suffix these
# rows with "(ttm)"/"(mrq)", unlike the flat-section labels.
_VALUATION_MAP: dict[str, tuple[str, _Converter]] = {
    "Market Cap": ("market_cap", _to_magnitude),
    "Enterprise Value": ("enterprise_value", _to_magnitude),
    "Trailing P/E": ("trailing_pe", _to_float),
    "Forward P/E": ("forward_pe", _to_float),
    "PEG Ratio (5yr expected)": ("peg_ratio", _to_float),
    "Price/Sales": ("price_to_sales", _to_float),
    "Price/Book": ("price_to_book", _to_float),
    "Enterprise Value/Revenue": ("ev_to_revenue", _to_float),
    "Enterprise Value/EBITDA": ("ev_to_ebitda", _to_float),
}


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


def _parse_valuation_table(
    doc: HTMLParser,
) -> tuple[dict[str, float | None], list[QuarterlyValuation]]:
    """Parse Yahoo's Valuation Measures historical grid.

    Yahoo renders this section as a ``<table>`` whose ``<thead>`` has a
    single ``<tr>`` with 7 ``<th>`` cells — an empty corner cell followed
    by 6 period labels ("Current" + 5 historical quarter dates). The
    ``<tbody>`` has one ``<tr>`` per metric with 7 ``<td>`` cells: a
    label cell followed by 6 value cells aligned with the header columns.

    Returns:
        snapshot: dict of StockMetrics field name -> value parsed from
                  the "Current" column (used to populate the top-level
                  StockMetrics valuation fields).
        history:  one QuarterlyValuation per period column (including
                  "Current"), in the left-to-right order Yahoo renders.
    """
    # 1. Find the header row that defines the period column labels. The
    #    valuation grid is the only <thead><tr> on the page with >= 6 <th>
    #    cells, so this selector is safe.
    period_labels: list[str] = []
    for tr in doc.css("thead tr"):
        th_cells = tr.css("th")
        if len(th_cells) >= 6:
            # First <th> is the empty corner cell; the rest are period labels.
            labels = [c.text(strip=True) for c in th_cells]
            # Drop the leading empty cell.
            period_labels = [label for label in labels[1:] if label]
            if period_labels:
                break

    if not period_labels:
        return {}, []

    # 2. Build one QuarterlyValuation per period column.
    histories: list[QuarterlyValuation] = [
        QuarterlyValuation(period=p) for p in period_labels
    ]

    # 3. Walk valuation rows and populate both snapshot + histories.
    #    A valuation row has 1 label <td> + N value <td>s where
    #    N == len(period_labels). Any row whose label isn't a known
    #    valuation metric is ignored.
    snapshot: dict[str, float | None] = {}
    expected_len = 1 + len(period_labels)
    for tr in doc.css("tr"):
        cells = tr.css("td")
        if len(cells) != expected_len:
            continue
        label = cells[0].text(strip=True)
        if label not in _VALUATION_MAP:
            continue
        field, converter = _VALUATION_MAP[label]
        for idx, value_cell in enumerate(cells[1:]):
            parsed = converter(value_cell.text(strip=True))
            setattr(histories[idx], field, parsed)
            if idx == 0:
                snapshot[field] = parsed

    return snapshot, histories


def _parse_document(html: str, ticker: str) -> StockMetrics | None:
    """Parse a Yahoo Key Statistics HTML page into a StockMetrics.

    Returns None on hard parse failure (root element missing). Otherwise
    returns a (possibly partial) StockMetrics populated from the flat
    statistics sections (Profitability, Management Effectiveness, Income
    Statement, Balance Sheet, Cash Flow, Stock Price History, and
    Dividends & Splits) plus the Valuation Measures historical grid
    (top-level snapshot fields + ``valuation_history``).
    """
    try:
        doc = HTMLParser(html)
    except Exception:
        return None
    if doc.body is None:
        return None

    rows = _parse_stat_rows(doc)
    flat_fields = _apply_flat_maps(rows)

    snapshot, history = _parse_valuation_table(doc)
    # Valuation-grid snapshot is authoritative for valuation fields
    # (market_cap, forward_pe, peg_ratio, etc.) because it reads the
    # "Current" column of the historical grid. Flat-map fields cover the
    # disjoint non-valuation sections. On any future overlap, prefer the
    # valuation-grid value.
    merged = {**flat_fields, **snapshot}

    return StockMetrics(
        ticker=ticker,
        valuation_history=history,
        **merged,
    )
