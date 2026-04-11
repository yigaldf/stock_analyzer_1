"""Helpers for reading/writing wizard state in st.session_state.

Centralizing this makes screens thin and testable (you can mock st.session_state).
"""

from __future__ import annotations

import streamlit as st

from app.models.schemas import StockInfo, StockMetrics
from app.services.scoring_service import DEFAULT_WEIGHTS

# Keys
STEP = "wizard_step"  # int: 1-4
TICKER = "selected_ticker"  # str | None
STOCK_INFO = "selected_info"  # StockInfo | None
PEER_CANDIDATES = "peer_candidates"  # list[str]
SELECTED_PEERS = "selected_peers"  # list[str]
METRICS_CACHE = "metrics_cache"  # dict[str, StockMetrics]
WEIGHTS = "weights"  # dict[str, float]
LAST_TOP_PICK = "last_top_pick"  # str | None
LAST_RECOMMENDATION = "last_recommendation"  # str | None


def init_state() -> None:
    """Initialize session_state with defaults if missing."""
    defaults: dict[str, object] = {
        STEP: 1,
        TICKER: None,
        STOCK_INFO: None,
        PEER_CANDIDATES: [],
        SELECTED_PEERS: [],
        METRICS_CACHE: {},
        WEIGHTS: dict(DEFAULT_WEIGHTS),
        LAST_TOP_PICK: None,
        LAST_RECOMMENDATION: None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def goto_step(n: int) -> None:
    st.session_state[STEP] = n


def set_ticker(ticker: str, info: StockInfo) -> None:
    # Clear downstream state only when switching to a different ticker
    if st.session_state.get(TICKER) != ticker:
        st.session_state[PEER_CANDIDATES] = []
        st.session_state[SELECTED_PEERS] = []
        st.session_state[METRICS_CACHE] = {}
        st.session_state[LAST_TOP_PICK] = None
        st.session_state[LAST_RECOMMENDATION] = None
    st.session_state[TICKER] = ticker
    st.session_state[STOCK_INFO] = info


def set_peer_candidates(tickers: list[str]) -> None:
    st.session_state[PEER_CANDIDATES] = tickers


def set_selected_peers(tickers: list[str]) -> None:
    st.session_state[SELECTED_PEERS] = tickers


def cache_metrics(ticker: str, metrics: StockMetrics) -> None:
    st.session_state[METRICS_CACHE][ticker] = metrics


def get_all_selected_metrics() -> list[StockMetrics]:
    """Return metrics for the selected stock + peers, in that order, skipping any missing."""
    tickers: list[str] = []
    if st.session_state.get(TICKER):
        tickers.append(st.session_state[TICKER])
    tickers.extend(st.session_state.get(SELECTED_PEERS, []))
    cache: dict[str, StockMetrics] = st.session_state.get(METRICS_CACHE, {})
    return [cache[t] for t in tickers if t in cache]


def set_weights(weights: dict[str, float]) -> None:
    st.session_state[WEIGHTS] = weights
