from app.models.schemas import StockMetrics
from app.services.scoring_service import (
    DEFAULT_WEIGHTS,
    compute_weighted_scores,
    score_category,
)


def _metrics(ticker: str, **overrides) -> StockMetrics:
    defaults = dict(
        ticker=ticker,
        forward_pe=None,
        trailing_pe=None,
        peg_ratio=None,
        price_to_sales=None,
        price_to_book=None,
        ev_to_revenue=None,
        ev_to_ebitda=None,
        market_cap=None,
        enterprise_value=None,
        profit_margin=None,
        operating_margin=None,
        roe=None,
        roa=None,
        revenue_growth_yoy=None,
        earnings_growth_yoy=None,
        debt_to_equity=None,
        current_ratio=None,
        total_cash=None,
        total_debt=None,
        operating_cash_flow=None,
        levered_free_cash_flow=None,
        beta=None,
        forward_dividend_yield=None,
        payout_ratio=None,
    )
    defaults.update(overrides)
    return StockMetrics(**defaults)


def test_valuation_lowest_pe_gets_5():
    stocks = [
        _metrics("A", forward_pe=10.0),
        _metrics("B", forward_pe=20.0),
        _metrics("C", forward_pe=30.0),
    ]
    scores = score_category("valuation", stocks)
    # Composite of (forward_pe, peg_ratio, ev_to_ebitda); only forward_pe set,
    # other sub-metrics dilute toward neutral 3.
    assert scores["A"].score == 4
    assert scores["C"].score == 2
    assert scores["B"].score == 3  # midpoint of composite


def test_growth_highest_revenue_growth_gets_5():
    stocks = [
        _metrics("A", revenue_growth_yoy=0.30),  # +30%
        _metrics("B", revenue_growth_yoy=0.10),  # +10%
        _metrics("C", revenue_growth_yoy=-0.05),  # -5%
    ]
    scores = score_category("growth", stocks)
    # Composite of (revenue_growth_yoy, earnings_growth_yoy); missing earnings
    # dilutes toward neutral 3.
    assert scores["A"].score == 4
    assert scores["C"].score == 2
    assert scores["B"].score == 3


def test_missing_data_gets_neutral_3():
    stocks = [
        _metrics("A", forward_pe=10.0),
        _metrics("B", forward_pe=None),
        _metrics("C", forward_pe=30.0),
    ]
    scores = score_category("valuation", stocks)
    assert scores["A"].score == 4
    assert scores["C"].score == 2
    assert scores["B"].score == 3
    # Composite display lists each sub-metric formatted; B has no data anywhere.
    assert "—" in scores["B"].display


def test_all_missing_all_neutral():
    stocks = [
        _metrics("A", forward_pe=None),
        _metrics("B", forward_pe=None),
    ]
    scores = score_category("valuation", stocks)
    assert scores["A"].score == 3
    assert scores["B"].score == 3


def test_single_stock_gets_5():
    # All three valuation sub-metrics populated → composite is genuinely 5.
    stocks = [_metrics("A", forward_pe=15.0, peg_ratio=1.0, ev_to_ebitda=8.0)]
    scores = score_category("valuation", stocks)
    assert scores["A"].score == 5


def test_health_lower_debt_equity_better():
    stocks = [
        _metrics("A", debt_to_equity=0.20),
        _metrics("B", debt_to_equity=0.80),
        _metrics("C", debt_to_equity=1.50),
    ]
    scores = score_category("health", stocks)
    # Composite of (debt_to_equity, current_ratio); only debt set.
    assert scores["A"].score == 4
    assert scores["B"].score == 3
    assert scores["C"].score == 2


def test_compute_weighted_scores_ranks_best_first():
    # A dominates valuation and growth; B is mediocre; C is worst everywhere
    stocks = [
        _metrics(
            "A",
            forward_pe=10.0,
            peg_ratio=0.8,
            ev_to_ebitda=7.0,
            revenue_growth_yoy=0.30,
            earnings_growth_yoy=0.25,
            operating_margin=0.20,
            profit_margin=0.18,
            roe=0.30,
            roa=0.15,
            debt_to_equity=0.20,
            current_ratio=2.5,
            levered_free_cash_flow=1.5e9,
            market_cap=20e9,
            forward_dividend_yield=0.03,
        ),
        _metrics(
            "B",
            forward_pe=20.0,
            peg_ratio=1.5,
            ev_to_ebitda=12.0,
            revenue_growth_yoy=0.10,
            earnings_growth_yoy=0.05,
            operating_margin=0.10,
            profit_margin=0.08,
            roe=0.15,
            roa=0.08,
            debt_to_equity=0.80,
            current_ratio=1.5,
            levered_free_cash_flow=8e8,
            market_cap=20e9,
            forward_dividend_yield=0.02,
        ),
        _metrics(
            "C",
            forward_pe=30.0,
            peg_ratio=2.5,
            ev_to_ebitda=20.0,
            revenue_growth_yoy=-0.05,
            earnings_growth_yoy=-0.10,
            operating_margin=0.02,
            profit_margin=0.01,
            roe=0.05,
            roa=0.02,
            debt_to_equity=1.50,
            current_ratio=0.8,
            levered_free_cash_flow=2e8,
            market_cap=20e9,
            forward_dividend_yield=0.01,
        ),
    ]
    rankings = compute_weighted_scores(stocks, DEFAULT_WEIGHTS)
    assert rankings[0].ticker == "A"
    assert rankings[0].rank == 1
    assert rankings[-1].ticker == "C"
    assert rankings[-1].rank == 3


def test_compute_weighted_scores_weights_change_order():
    # A has better valuation; B has better growth.
    stocks = [
        _metrics(
            "A",
            forward_pe=5.0,
            peg_ratio=0.5,
            ev_to_ebitda=5.0,
            revenue_growth_yoy=0.05,
            earnings_growth_yoy=0.05,
            operating_margin=0.10,
            profit_margin=0.10,
            roe=0.10,
            roa=0.10,
            debt_to_equity=0.50,
            current_ratio=1.5,
            forward_dividend_yield=0.02,
        ),
        _metrics(
            "B",
            forward_pe=50.0,
            peg_ratio=3.0,
            ev_to_ebitda=30.0,
            revenue_growth_yoy=0.50,
            earnings_growth_yoy=0.50,
            operating_margin=0.10,
            profit_margin=0.10,
            roe=0.10,
            roa=0.10,
            debt_to_equity=0.50,
            current_ratio=1.5,
            forward_dividend_yield=0.02,
        ),
    ]
    # Weight valuation heavily → A wins
    val_heavy = {
        "valuation": 1.0,
        "growth": 0.0,
        "profitability": 0.0,
        "capital_efficiency": 0.0,
        "health": 0.0,
        "cash_quality": 0.0,
        "valuation_trend": 0.0,
        "dividend": 0.0,
    }
    rankings_val = compute_weighted_scores(stocks, val_heavy)
    assert rankings_val[0].ticker == "A"

    # Weight growth heavily → B wins
    growth_heavy = {
        "valuation": 0.0,
        "growth": 1.0,
        "profitability": 0.0,
        "capital_efficiency": 0.0,
        "health": 0.0,
        "cash_quality": 0.0,
        "valuation_trend": 0.0,
        "dividend": 0.0,
    }
    rankings_growth = compute_weighted_scores(stocks, growth_heavy)
    assert rankings_growth[0].ticker == "B"


def test_ties_broken_alphabetically():
    # Identical metrics → same weighted score → alphabetical tie-break
    stocks = [
        _metrics(
            "Z",
            forward_pe=10.0,
            peg_ratio=1.0,
            ev_to_ebitda=8.0,
            revenue_growth_yoy=0.10,
            earnings_growth_yoy=0.10,
            operating_margin=0.10,
            profit_margin=0.10,
            roe=0.10,
            roa=0.10,
            debt_to_equity=0.50,
            current_ratio=1.5,
            forward_dividend_yield=0.02,
        ),
        _metrics(
            "A",
            forward_pe=10.0,
            peg_ratio=1.0,
            ev_to_ebitda=8.0,
            revenue_growth_yoy=0.10,
            earnings_growth_yoy=0.10,
            operating_margin=0.10,
            profit_margin=0.10,
            roe=0.10,
            roa=0.10,
            debt_to_equity=0.50,
            current_ratio=1.5,
            forward_dividend_yield=0.02,
        ),
    ]
    rankings = compute_weighted_scores(stocks, DEFAULT_WEIGHTS)
    # Both have equal weighted_score; A comes first alphabetically
    assert rankings[0].ticker == "A"
    assert rankings[1].ticker == "Z"


def test_weights_are_normalized_if_not_sum_to_one():
    stocks = [
        _metrics(
            "A",
            forward_pe=10.0,
            peg_ratio=1.0,
            ev_to_ebitda=8.0,
            revenue_growth_yoy=0.10,
            earnings_growth_yoy=0.10,
            operating_margin=0.10,
            profit_margin=0.10,
            roe=0.10,
            roa=0.10,
            debt_to_equity=0.50,
            current_ratio=1.5,
            forward_dividend_yield=0.02,
        ),
        _metrics(
            "B",
            forward_pe=30.0,
            peg_ratio=2.0,
            ev_to_ebitda=15.0,
            revenue_growth_yoy=0.05,
            earnings_growth_yoy=0.05,
            operating_margin=0.05,
            profit_margin=0.05,
            roe=0.05,
            roa=0.05,
            debt_to_equity=1.00,
            current_ratio=1.0,
            forward_dividend_yield=0.01,
        ),
    ]
    # These weights sum to 2.0 — should be normalized internally
    doubled = {k: v * 2 for k, v in DEFAULT_WEIGHTS.items()}
    normal = compute_weighted_scores(stocks, DEFAULT_WEIGHTS)
    doubled_result = compute_weighted_scores(stocks, doubled)
    # Same ordering either way
    assert [r.ticker for r in normal] == [r.ticker for r in doubled_result]
    # Weighted scores are equal (normalized)
    for n, d in zip(normal, doubled_result):
        assert abs(n.weighted_score - d.weighted_score) < 1e-9
