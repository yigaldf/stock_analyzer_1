from __future__ import annotations

import streamlit as st

from app.agents.peers_agent import suggest_peers
from app.services.stock_service import validate_tickers
from app.ui import nav, state


def _load_candidates() -> None:
    """Call the peer agent and populate candidates if not already loaded."""
    if st.session_state.get(state.PEER_CANDIDATES):
        return
    info = st.session_state.get(state.STOCK_INFO)
    if info is None:
        return
    with st.spinner("Finding competitors..."):
        raw = suggest_peers(info.ticker, info.name, info.sector)
        validated = validate_tickers(raw) if raw else []
    state.set_peer_candidates(validated)


def render() -> None:
    nav.progress_header(2)
    info = st.session_state.get(state.STOCK_INFO)
    if info is None:
        st.warning("Please select a stock first.")
        nav.nav_buttons(2, next_enabled=False)
        return

    st.write(
        f"AI-suggested competitors for **{info.ticker}** ({info.name}). "
        "Select between 1 and 7."
    )

    _load_candidates()
    candidates: list[str] = st.session_state.get(state.PEER_CANDIDATES, [])

    if not candidates:
        st.warning(
            "Couldn't suggest competitors automatically. "
            "Enter them manually below (comma-separated)."
        )
        manual = st.text_input("Tickers", key="step2_manual", placeholder="NKE, ADDYY, UA")
        if manual:
            tickers = [t.strip().upper() for t in manual.split(",") if t.strip()]
            with st.spinner("Validating tickers..."):
                candidates = validate_tickers(tickers)
            state.set_peer_candidates(candidates)

    # Checkbox list
    selected = list(st.session_state.get(state.SELECTED_PEERS, []))
    if candidates:
        st.write("")
        new_selected: list[str] = []
        cols = st.columns(2)
        for i, t in enumerate(candidates):
            with cols[i % 2]:
                checked = st.checkbox(
                    t,
                    value=(t in selected),
                    key=f"peer_cb_{t}",
                )
                if checked:
                    new_selected.append(t)
        selected = new_selected
        state.set_selected_peers(selected)

    # Validation messages
    next_enabled = False
    if len(selected) == 0:
        if candidates:
            st.info("Select at least 1 competitor to continue.")
    elif len(selected) > 7:
        st.error(f"You selected {len(selected)} competitors. Maximum is 7.")
    else:
        next_enabled = True

    nav.nav_buttons(2, next_enabled=next_enabled)
