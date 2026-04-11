"""Dedicated tests for the two derived scoring categories.

- cash_quality: FCF yield (levered_free_cash_flow / market_cap), higher better
- valuation_trend: current forward_pe / mean historical forward_pe (excluding
  the "Current" entry), lower better
"""
from app.models.schemas import QuarterlyValuation, StockMetrics
from app.services.scoring_service import score_category


def _m(ticker: str, **kwargs) -> StockMetrics:
    """Shorthand StockMetrics builder for tests — everything else defaults."""
    return StockMetrics(ticker=ticker, **kwargs)


# ---------------------------------------------------------------------------
# Cash Quality
# ---------------------------------------------------------------------------


def test_cash_quality_higher_fcf_yield_wins():
    stocks = [
        _m("A", levered_free_cash_flow=2_000_000_000, market_cap=10_000_000_000),  # 20%
        _m("B", levered_free_cash_flow=500_000_000,   market_cap=10_000_000_000),  # 5%
        _m("C", levered_free_cash_flow=100_000_000,   market_cap=10_000_000_000),  # 1%
    ]
    scores = score_category("cash_quality", stocks)
    assert scores["A"].score == 5
    assert scores["B"].score == 3
    assert scores["C"].score == 1
    # Display should include the computed yield.
    assert "20.0%" in scores["A"].display


def test_cash_quality_missing_fcf_is_neutral():
    stocks = [
        _m("A", levered_free_cash_flow=1_000_000_000, market_cap=10_000_000_000),
        _m("B", levered_free_cash_flow=None,          market_cap=10_000_000_000),
    ]
    scores = score_category("cash_quality", stocks)
    assert scores["A"].score == 5  # only peer with valid yield
    assert scores["B"].score == 3


def test_cash_quality_missing_market_cap_is_neutral():
    stocks = [
        _m("A", levered_free_cash_flow=1_000_000_000, market_cap=10_000_000_000),
        _m("B", levered_free_cash_flow=1_000_000_000, market_cap=None),
    ]
    scores = score_category("cash_quality", stocks)
    assert scores["A"].score == 5
    assert scores["B"].score == 3


def test_cash_quality_zero_market_cap_is_neutral():
    """Protect against division by zero."""
    stocks = [
        _m("A", levered_free_cash_flow=1_000_000_000, market_cap=10_000_000_000),
        _m("B", levered_free_cash_flow=1_000_000_000, market_cap=0),
    ]
    scores = score_category("cash_quality", stocks)
    assert scores["B"].score == 3
    assert scores["B"].raw_value is None


def test_cash_quality_all_peers_missing_is_neutral_for_all():
    stocks = [
        _m("A", levered_free_cash_flow=None, market_cap=None),
        _m("B", levered_free_cash_flow=None, market_cap=None),
    ]
    scores = score_category("cash_quality", stocks)
    assert scores["A"].score == 3
    assert scores["B"].score == 3


# ---------------------------------------------------------------------------
# Valuation Trend
# ---------------------------------------------------------------------------


def test_valuation_trend_cheaper_than_history_wins():
    """A is cheaper than its own history (ratio ~0.5).
    B is more expensive (ratio ~1.5). Lower ratio wins."""
    a = _m(
        "A",
        forward_pe=10.0,
        valuation_history=[
            QuarterlyValuation(period="Current", forward_pe=10.0),
            QuarterlyValuation(period="12/31/2025", forward_pe=18.0),
            QuarterlyValuation(period="9/30/2025", forward_pe=22.0),
        ],
    )
    b = _m(
        "B",
        forward_pe=30.0,
        valuation_history=[
            QuarterlyValuation(period="Current", forward_pe=30.0),
            QuarterlyValuation(period="12/31/2025", forward_pe=18.0),
            QuarterlyValuation(period="9/30/2025", forward_pe=22.0),
        ],
    )
    scores = score_category("valuation_trend", [a, b])
    assert scores["A"].score == 5
    assert scores["B"].score == 1
    # Display format references the ratio.
    assert "0.50" in scores["A"].display


def test_valuation_trend_excludes_current_from_historical_mean():
    """If 'Current' leaks into the historical mean, the ratio would be
    12 / ((12+18+22)/3) = 12/17.33 = 0.69 (not 0.60). Excluding
    'Current' correctly gives 12 / ((18+22)/2) = 12/20 = 0.60."""
    a = _m(
        "A",
        forward_pe=12.0,
        valuation_history=[
            QuarterlyValuation(period="Current", forward_pe=12.0),
            QuarterlyValuation(period="12/31/2025", forward_pe=18.0),
            QuarterlyValuation(period="9/30/2025", forward_pe=22.0),
        ],
    )
    scores = score_category("valuation_trend", [a])
    assert scores["A"].raw_value is not None
    assert abs(scores["A"].raw_value - 0.6) < 0.001


def test_valuation_trend_missing_history_is_neutral():
    a = _m("A", forward_pe=10.0, valuation_history=[])
    b = _m(
        "B",
        forward_pe=20.0,
        valuation_history=[
            QuarterlyValuation(period="Current", forward_pe=20.0),
            QuarterlyValuation(period="12/31/2025", forward_pe=10.0),
        ],
    )
    scores = score_category("valuation_trend", [a, b])
    assert scores["A"].score == 3
    # B has valid history: ratio = 20 / 10 = 2.0. Only valid peer → single
    # valid scorer gets 5.
    assert scores["B"].score == 5


def test_valuation_trend_only_current_in_history_is_neutral():
    """When every historical entry is labeled 'Current' (e.g. only one
    column), the historical mean is undefined → neutral 3."""
    a = _m(
        "A",
        forward_pe=10.0,
        valuation_history=[
            QuarterlyValuation(period="Current", forward_pe=10.0),
        ],
    )
    scores = score_category("valuation_trend", [a])
    assert scores["A"].score == 3


def test_valuation_trend_missing_current_forward_pe_is_neutral():
    """If the top-level forward_pe is None, we can't compute a ratio even
    if history exists — receive neutral 3."""
    a = _m(
        "A",
        forward_pe=None,
        valuation_history=[
            QuarterlyValuation(period="Current", forward_pe=None),
            QuarterlyValuation(period="12/31/2025", forward_pe=18.0),
        ],
    )
    scores = score_category("valuation_trend", [a])
    assert scores["A"].score == 3


def test_valuation_trend_zero_historical_mean_is_neutral():
    """Guard against division by zero when every historical forward_pe is 0."""
    a = _m(
        "A",
        forward_pe=10.0,
        valuation_history=[
            QuarterlyValuation(period="Current", forward_pe=10.0),
            QuarterlyValuation(period="12/31/2025", forward_pe=0.0),
            QuarterlyValuation(period="9/30/2025", forward_pe=0.0),
        ],
    )
    scores = score_category("valuation_trend", [a])
    assert scores["A"].score == 3


def test_valuation_trend_all_peers_missing_is_neutral_for_all():
    a = _m("A", forward_pe=None, valuation_history=[])
    b = _m("B", forward_pe=None, valuation_history=[])
    scores = score_category("valuation_trend", [a, b])
    assert scores["A"].score == 3
    assert scores["B"].score == 3
