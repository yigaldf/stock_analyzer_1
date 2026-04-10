from __future__ import annotations

import pandas as pd
import streamlit as st

from app.agents.recommendation_agent import generate_recommendation
from app.services.scoring_service import CATEGORIES, DEFAULT_WEIGHTS, compute_weighted_scores
from app.ui import nav, state

_CATEGORY_LABELS = {
    "valuation": "Valuation (fwd P/E)",
    "growth": "Revenue Growth",
    "profitability": "Profitability (op margin)",
    "roic": "ROIC (ROE)",
    "health": "Financial Health (D/E)",
    "dividend": "Dividend Yield",
}


def _render_weight_sliders() -> dict[str, float]:
    st.markdown("#### Weights")
    current = st.session_state.get(state.WEIGHTS, dict(DEFAULT_WEIGHTS))
    cols = st.columns(3)
    new_weights: dict[str, float] = {}
    for i, cat in enumerate(CATEGORIES):
        with cols[i % 3]:
            pct = st.slider(
                _CATEGORY_LABELS[cat],
                min_value=0,
                max_value=100,
                value=int(round(current.get(cat, 0) * 100)),
                step=5,
                key=f"weight_slider_{cat}",
            )
            new_weights[cat] = pct / 100
    return new_weights


def render() -> None:
    nav.progress_header(4)
    metrics = state.get_all_selected_metrics()
    if not metrics:
        st.warning("No metrics available. Go back and select stocks first.")
        nav.nav_buttons(4, next_enabled=False)
        return

    weights = _render_weight_sliders()
    state.set_weights(weights)

    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:
        st.warning(
            f"Weights total {total*100:.0f}% — adjust to 100% for an exact balance. "
            "Ranking uses normalized weights."
        )

    if sum(weights.values()) <= 0:
        st.error("At least one category must have a non-zero weight.")
        nav.nav_buttons(4)
        return

    rankings = compute_weighted_scores(metrics, weights)

    # Ranking table
    rows = []
    for r in rankings:
        row = {"Rank": f"#{r.rank}", "Ticker": r.ticker, "Weighted Score": f"{r.weighted_score:.2f}"}
        for cs in r.category_scores:
            row[_CATEGORY_LABELS[cs.category]] = f"{cs.score}/5"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Only regenerate narrative when top pick changes
    top_ticker = rankings[0].ticker
    last_top = st.session_state.get(state.LAST_TOP_PICK)
    last_text = st.session_state.get(state.LAST_RECOMMENDATION)
    if last_top != top_ticker or last_text is None:
        with st.spinner("Generating AI recommendation..."):
            narrative = generate_recommendation(rankings, weights)
        st.session_state[state.LAST_TOP_PICK] = top_ticker
        st.session_state[state.LAST_RECOMMENDATION] = narrative
    else:
        narrative = last_text

    st.markdown("### 🤖 AI Recommendation")
    st.info(narrative)

    nav.nav_buttons(4)
