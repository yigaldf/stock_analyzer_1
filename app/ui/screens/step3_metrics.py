from __future__ import annotations

from typing import Callable

import pandas as pd
import streamlit as st

from app.models.schemas import StockMetrics
from app.services.stock_service import get_stock_metrics
from app.ui import nav, state

# (display name, attr, formatter)
_METRIC_ROWS: list[tuple[str, str, Callable[[float], str]]] = [
    ("Fwd P/E", "forward_pe", lambda v: f"{v:.1f}x"),
    ("Trailing P/E", "trailing_pe", lambda v: f"{v:.1f}x"),
    ("PEG", "peg_ratio", lambda v: f"{v:.2f}"),
    ("P/S", "price_to_sales", lambda v: f"{v:.1f}"),
    ("Market cap", "market_cap", lambda v: f"${v/1e9:.1f}B"),
    ("Rev growth", "revenue_growth", lambda v: f"{v*100:.1f}%"),
    ("EPS growth", "eps_growth", lambda v: f"{v*100:.1f}%"),
    ("Op margin", "operating_margin", lambda v: f"{v*100:.1f}%"),
    ("Profit margin", "profit_margin", lambda v: f"{v*100:.1f}%"),
    ("ROE", "roe", lambda v: f"{v*100:.1f}%"),
    ("D/E", "debt_to_equity", lambda v: f"{v:.2f}"),
    ("Beta", "beta", lambda v: f"{v:.2f}"),
    ("Div yield", "dividend_yield", lambda v: f"{v*100:.2f}%"),
]


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

    st.write("Side-by-side comparison of 12 key metrics.")

    # Build a dataframe: rows = metrics, columns = tickers
    data: dict[str, list[str]] = {"Metric": [row[0] for row in _METRIC_ROWS]}
    for m in metrics_list:
        data[m.ticker] = [
            _format(getattr(m, attr), fmt) for _, attr, fmt in _METRIC_ROWS
        ]
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    nav.nav_buttons(3, next_enabled=True)
