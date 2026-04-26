from __future__ import annotations

from typing import Callable

import pandas as pd
import streamlit as st

from app.models.schemas import StockMetrics
from app.services.stock_service import get_stock_metrics
from app.ui import nav, state

# Each group is (section label, list of (display name, attr, formatter) rows).
_METRIC_GROUPS: list[tuple[str, list[tuple[str, str, Callable[[float], str]]]]] = [
    (
        "Valuation",
        [
            ("Forward P/E", "forward_pe", lambda v: f"{v:.1f}x"),
            ("Trailing P/E", "trailing_pe", lambda v: f"{v:.1f}x"),
            ("PEG (5Y)", "peg_ratio", lambda v: f"{v:.2f}"),
            ("Price/Sales", "price_to_sales", lambda v: f"{v:.1f}"),
            ("Price/Book", "price_to_book", lambda v: f"{v:.1f}"),
            ("EV/EBITDA", "ev_to_ebitda", lambda v: f"{v:.1f}"),
            ("EV/Revenue", "ev_to_revenue", lambda v: f"{v:.1f}"),
        ],
    ),
    (
        "Profitability",
        [
            ("Operating Margin", "operating_margin", lambda v: f"{v * 100:.1f}%"),
            ("Profit Margin", "profit_margin", lambda v: f"{v * 100:.1f}%"),
        ],
    ),
    (
        "Capital Efficiency",
        [
            ("ROE", "roe", lambda v: f"{v * 100:.1f}%"),
            ("ROA", "roa", lambda v: f"{v * 100:.1f}%"),
        ],
    ),
    (
        "Growth",
        [
            ("Revenue Growth (yoy)", "revenue_growth_yoy", lambda v: f"{v * 100:.1f}%"),
            (
                "Earnings Growth (yoy)",
                "earnings_growth_yoy",
                lambda v: f"{v * 100:.1f}%",
            ),
        ],
    ),
    (
        "Financial Health",
        [
            ("Debt/Equity", "debt_to_equity", lambda v: f"{v * 100:.1f}%"),
            ("Current Ratio", "current_ratio", lambda v: f"{v:.2f}"),
            ("Total Cash", "total_cash", lambda v: f"${v / 1e9:.2f}B"),
            ("Total Debt", "total_debt", lambda v: f"${v / 1e9:.2f}B"),
        ],
    ),
    (
        "Cash Flow",
        [
            (
                "Operating Cash Flow",
                "operating_cash_flow",
                lambda v: f"${v / 1e9:.2f}B",
            ),
            (
                "Levered Free Cash Flow",
                "levered_free_cash_flow",
                lambda v: f"${v / 1e9:.2f}B",
            ),
        ],
    ),
    (
        "Market Context",
        [
            ("Beta (5Y)", "beta", lambda v: f"{v:.2f}"),
            ("Market Cap", "market_cap", lambda v: f"${v / 1e9:.2f}B"),
            ("Enterprise Value", "enterprise_value", lambda v: f"${v / 1e9:.2f}B"),
        ],
    ),
    (
        "Dividend",
        [
            (
                "Forward Dividend Yield",
                "forward_dividend_yield",
                lambda v: f"{v * 100:.2f}%",
            ),
            ("Payout Ratio", "payout_ratio", lambda v: f"{v * 100:.1f}%"),
        ],
    ),
]


# Stylesheet: preserves the existing .metrics-table look from the pre-Task-11
# single-table version, plus a .source-badge pill rendered above each ticker
# column so users can see which fetch backend produced the row.
_STEP3_CSS = """
<style>
.metrics-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 1.1rem;
    margin: 0.25rem 0 1rem 0;
}
.metrics-table th,
.metrics-table td {
    padding: 8px 12px;
    border-bottom: 1px solid rgba(128, 128, 128, 0.25);
    text-align: right;
    white-space: nowrap;
}
.metrics-table th {
    background-color: rgba(128, 128, 128, 0.08);
    font-weight: 600;
    text-align: center;
}
.metrics-table th:first-child,
.metrics-table td:first-child {
    text-align: left;
    font-weight: 600;
    width: 140px;
    max-width: 140px;
}
.metrics-table tr:hover {
    background-color: rgba(128, 128, 128, 0.06);
}
.source-badges {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
    margin: 0.25rem 0 0.75rem 0;
    font-size: 0.9rem;
}
.source-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 2px 10px;
    border-radius: 999px;
    font-weight: 500;
}
.source-badge.httpx {
    background-color: rgba(46, 160, 67, 0.18);
    color: #2ea043;
    border: 1px solid rgba(46, 160, 67, 0.4);
}
.source-badge.playwright {
    background-color: rgba(212, 136, 6, 0.18);
    color: #d48806;
    border: 1px solid rgba(212, 136, 6, 0.4);
}
.source-badge.unknown {
    background-color: rgba(128, 128, 128, 0.18);
    color: #888;
    border: 1px solid rgba(128, 128, 128, 0.4);
}
</style>
"""


def _format(value: float | None, fmt: Callable[[float], str]) -> str:
    if value is None:
        return "—"
    try:
        return fmt(value)
    except Exception:
        return "—"


def _fetch_all_metrics() -> list[str]:
    """Fetch metrics for the selected stock + peers. Returns list of fetch errors."""
    errors: list[str] = []
    all_tickers: list[str] = []
    if st.session_state.get(state.TICKER):
        all_tickers.append(st.session_state[state.TICKER])
    all_tickers.extend(st.session_state.get(state.SELECTED_PEERS, []))

    cache: dict[str, StockMetrics] = st.session_state.get(state.METRICS_CACHE, {})
    for t in all_tickers:
        if t in cache:
            continue
        m = get_stock_metrics(t)
        if m is None:
            errors.append(t)
        else:
            state.cache_metrics(t, m)
    return errors


def _source_badge_html(metrics_list: list[StockMetrics]) -> str:
    """Render a row of pill-shaped badges, one per ticker, showing which
    backend produced each stock's metrics (httpx fast path or playwright
    fallback). Rendered once above the grouped tables."""
    parts: list[str] = ['<div class="source-badges">']
    for m in metrics_list:
        if m.source == "httpx":
            cls = "httpx"
            text = f"⚡ {m.ticker} via httpx"
        elif m.source == "playwright":
            cls = "playwright"
            text = f"🎭 {m.ticker} via playwright"
        else:
            cls = "unknown"
            text = f"— {m.ticker} (source unknown)"
        parts.append(f'<span class="source-badge {cls}">{text}</span>')
    parts.append("</div>")
    return "".join(parts)


def _render_all_metrics(metrics_list: list[StockMetrics]) -> None:
    """Render a single combined table with company name row and all metric groups."""
    # Build all row labels and values
    labels: list[str] = ["Company"]
    values_by_ticker: dict[str, list[str]] = {
        m.ticker: [(m.name or "—")[:12]] for m in metrics_list
    }

    for group_name, rows in _METRIC_GROUPS:
        # Section header row
        labels.append(f"<b>{group_name}</b>")
        for m in metrics_list:
            values_by_ticker[m.ticker].append("")
        # Metric rows
        for display_name, attr, fmt in rows:
            labels.append(display_name)
            for m in metrics_list:
                values_by_ticker[m.ticker].append(
                    _format(getattr(m, attr), fmt)
                )

    data: dict[str, list[str]] = {"Metric": labels}
    for m in metrics_list:
        data[m.ticker] = values_by_ticker[m.ticker]

    df = pd.DataFrame(data)
    st.markdown(
        df.to_html(index=False, classes="metrics-table", escape=False),
        unsafe_allow_html=True,
    )


def _render_forward_pe_trend(metrics_list: list[StockMetrics]) -> None:
    """Render a 5-quarter Forward P/E trend chart, one line per peer.

    Silently skipped if no peer has valuation_history or if peers' period
    label lists disagree (different fiscal calendars).
    """
    histories = [m for m in metrics_list if m.valuation_history]
    if not histories:
        return

    reference_periods = [q.period for q in histories[0].valuation_history]
    if any(
        [q.period for q in m.valuation_history] != reference_periods for m in histories
    ):
        return  # period mismatch — skip rather than render misleading chart

    chart_data: dict[str, list[float | None]] = {}
    for m in histories:
        chart_data[m.ticker] = [q.forward_pe for q in m.valuation_history]
    trend_df = pd.DataFrame(chart_data, index=reference_periods)

    st.markdown("##### Forward P/E trend (current + recent quarters)")
    st.line_chart(trend_df)


def render() -> None:
    nav.progress_header(3)
    if not st.session_state.get(state.SELECTED_PEERS):
        st.warning("Please select peers first.")
        nav.nav_buttons(3, next_enabled=False)
        return

    with st.spinner("Fetching financial metrics..."):
        errors = _fetch_all_metrics()
    if errors:
        st.warning(f"Couldn't fetch metrics for: {', '.join(errors)}")

    metrics_list = state.get_all_selected_metrics()
    if not metrics_list:
        st.error("No metrics available.")
        nav.nav_buttons(3, next_enabled=False)
        return

    st.write("Side-by-side comparison of fundamentals from Yahoo Key Statistics.")

    # Inject stylesheet once per render.
    st.markdown(_STEP3_CSS, unsafe_allow_html=True)

    # Source badges — shows which fetch backend produced each ticker's row.
    st.markdown(_source_badge_html(metrics_list), unsafe_allow_html=True)

    # Single combined comparison table.
    _render_all_metrics(metrics_list)

    # Forward P/E trend chart below the tables.
    _render_forward_pe_trend(metrics_list)

    nav.nav_buttons(3, next_enabled=True)
