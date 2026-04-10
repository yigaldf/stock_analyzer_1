"""Entry point for the Finance Stock Comparison wizard.

Run with: uv run streamlit run streamlit_app.py
"""
from __future__ import annotations

import streamlit as st

from app.ui import state
from app.ui.screens import step1_select, step2_peers, step3_metrics, step4_ranking


def main() -> None:
    st.set_page_config(
        page_title="Stock Analyzer",
        page_icon="📈",
        layout="wide",
    )
    st.title("📈 Stock Analyzer")
    state.init_state()

    step = st.session_state.get(state.STEP, 1)
    if step == 1:
        step1_select.render()
    elif step == 2:
        step2_peers.render()
    elif step == 3:
        step3_metrics.render()
    elif step == 4:
        step4_ranking.render()
    else:
        st.error(f"Unknown step: {step}")


if __name__ == "__main__":
    main()
