from __future__ import annotations

import streamlit as st

from app.services.stock_service import get_stock_info
from app.ui import nav, state


def render() -> None:
    nav.progress_header(1)
    st.write("Enter a stock ticker to begin.")

    ticker_input = st.text_input(
        "Ticker symbol",
        value=st.session_state.get(state.TICKER) or "",
        placeholder="e.g. LULU",
        key="step1_ticker_input",
    ).upper().strip()

    info = None
    if ticker_input:
        with st.spinner(f"Looking up {ticker_input}..."):
            info = get_stock_info(ticker_input)

        if info is None:
            st.error(f"Ticker '{ticker_input}' not found. Try another symbol.")
        else:
            state.set_ticker(ticker_input, info)
            st.success(f"Found: **{info.name}**")
            col1, col2 = st.columns(2)
            col1.metric("Sector", info.sector)
            col2.metric("Current price", f"${info.current_price:,.2f}")

    nav.nav_buttons(1, next_enabled=info is not None)
