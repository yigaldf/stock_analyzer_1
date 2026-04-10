"""Wizard progress indicator and back/next button bar."""
from __future__ import annotations

import streamlit as st

from app.ui import state

STEP_LABELS = ["Select Stock", "Pick Competitors", "Compare Metrics", "Rank & Recommend"]


def progress_header(current_step: int) -> None:
    st.markdown(f"### Step {current_step} of 4 — {STEP_LABELS[current_step - 1]}")
    st.progress(current_step / 4)


def nav_buttons(
    current_step: int,
    *,
    next_enabled: bool = True,
    next_label: str = "Next →",
) -> None:
    """Render Back/Next buttons at the bottom of a screen."""
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
