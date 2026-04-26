"""Wizard progress indicator and back/next button bar."""

from __future__ import annotations

import streamlit as st

from app.ui import state

STEP_LABELS = [
    "Select Stock",
    "Pick Competitors",
    "Compare Metrics",
    "Rank & Recommend",
]


def progress_header(current_step: int) -> None:
    st.markdown(f"### Step {current_step} of 4 — {STEP_LABELS[current_step - 1]}")
    st.progress(current_step / 4)


_NAV_CSS = """
<style>
/* Green enabled nav buttons */
div[data-testid="column"] button[kind="secondary"]:not(:disabled) {
    background-color: #2ea043;
    color: white;
    border: 1px solid #2ea043;
}
div[data-testid="column"] button[kind="secondary"]:not(:disabled):hover {
    background-color: #238636;
    border-color: #238636;
}
/* Gray disabled nav buttons */
div[data-testid="column"] button[kind="secondary"]:disabled {
    background-color: #6c757d;
    color: #ccc;
    border: 1px solid #6c757d;
}
</style>
"""


def nav_buttons(
    current_step: int,
    *,
    next_enabled: bool = True,
    next_label: str = "Next →",
) -> None:
    """Render Back/Next buttons at the bottom of a screen."""
    st.markdown(_NAV_CSS, unsafe_allow_html=True)
    col_back, col_spacer, col_next = st.columns([1, 3, 1])
    with col_back:
        if current_step > 1:
            if st.button("← Back", key=f"back_{current_step}"):
                state.goto_step(current_step - 1)
                st.rerun()
    with col_next:
        if current_step < 4:
            if st.button(
                next_label,
                key=f"next_{current_step}",
                disabled=not next_enabled,
            ):
                state.goto_step(current_step + 1)
                st.rerun()
