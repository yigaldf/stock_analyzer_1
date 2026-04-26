from __future__ import annotations

import pandas as pd
import streamlit as st

from app.agents.recommendation_agent import generate_recommendation
from app.services.scoring_service import (
    CATEGORIES,
    DEFAULT_WEIGHTS,
    compute_weighted_scores,
)
from app.ui import nav, state

_CATEGORY_LABELS = {
    "valuation": "Valuation",
    "growth": "Growth",
    "profitability": "Profitability",
    "capital_efficiency": "Capital Efficiency",
    "health": "Financial Health",
    "cash_quality": "Cash Quality",
    "valuation_trend": "Valuation Trend",
    "dividend": "Dividend",
}


def _rebalance_weights(changed_cat: str, new_pct: int) -> None:
    """Redistribute weight change across other categories proportionally."""
    weights_pct: dict[str, int] = st.session_state.get("_weights_pct", {})
    if not weights_pct:
        return

    old_pct = weights_pct.get(changed_cat, 0)
    delta = new_pct - old_pct
    if delta == 0:
        return

    weights_pct[changed_cat] = new_pct

    # Remaining budget the other sliders must share
    others = [c for c in CATEGORIES if c != changed_cat]
    other_total = sum(weights_pct[c] for c in others)

    if other_total == 0:
        # All others are zero — spread the deficit evenly
        per_cat = (100 - new_pct) // len(others)
        remainder = (100 - new_pct) - per_cat * len(others)
        for j, c in enumerate(others):
            weights_pct[c] = per_cat + (1 if j < remainder else 0)
    else:
        target_other_total = 100 - new_pct
        # Proportional redistribution
        scaled = {c: weights_pct[c] * target_other_total / other_total for c in others}
        # Round to integers that sum exactly to target_other_total
        floored = {c: int(v) for c, v in scaled.items()}
        remainder = target_other_total - sum(floored.values())
        fracs = sorted(others, key=lambda c: scaled[c] - floored[c], reverse=True)
        for j, c in enumerate(fracs):
            floored[c] += 1 if j < remainder else 0
        for c in others:
            weights_pct[c] = max(0, floored[c])

    st.session_state["_weights_pct"] = weights_pct
    # Sync slider keys
    for c in CATEGORIES:
        st.session_state[f"weight_slider_{c}"] = weights_pct[c]


def _render_weight_sliders() -> dict[str, float]:
    st.markdown("#### Weights")
    current = st.session_state.get(state.WEIGHTS, dict(DEFAULT_WEIGHTS))

    # Initialize internal pct tracker once
    if "_weights_pct" not in st.session_state:
        st.session_state["_weights_pct"] = {
            cat: int(round(current.get(cat, 0) * 100)) for cat in CATEGORIES
        }

    weights_pct: dict[str, int] = st.session_state["_weights_pct"]

    # Detect which slider changed and rebalance
    for cat in CATEGORIES:
        key = f"weight_slider_{cat}"
        if key in st.session_state and st.session_state[key] != weights_pct[cat]:
            _rebalance_weights(cat, st.session_state[key])
            break

    weights_pct = st.session_state["_weights_pct"]

    cols = st.columns(3)
    new_weights: dict[str, float] = {}
    for i, cat in enumerate(CATEGORIES):
        with cols[i % 3]:
            pct = st.slider(
                _CATEGORY_LABELS[cat],
                min_value=0,
                max_value=100,
                value=weights_pct[cat],
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
            f"Weights total {total * 100:.0f}% — adjust to 100% for an exact balance. "
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
        row = {
            "Rank": f"#{r.rank}",
            "Ticker": r.ticker,
            "Weighted Score": f"{r.weighted_score:.2f}",
        }
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
