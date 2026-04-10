from app.models.schemas import StockMetrics
from app.services.scoring_service import DEFAULT_WEIGHTS, compute_weighted_scores, score_category


def _metrics(ticker: str, **overrides) -> StockMetrics:
    defaults = dict(
        ticker=ticker,
        forward_pe=None, trailing_pe=None, peg_ratio=None, price_to_sales=None,
        market_cap=None, profit_margin=None, operating_margin=None,
        revenue_growth=None, eps_growth=None, roe=None, debt_to_equity=None,
        beta=None, dividend_yield=None,
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
    assert scores["A"].score == 5
    assert scores["C"].score == 1
    assert scores["B"].score == 3  # midpoint


def test_growth_highest_revenue_growth_gets_5():
    stocks = [
        _metrics("A", revenue_growth=0.30),  # +30%
        _metrics("B", revenue_growth=0.10),  # +10%
        _metrics("C", revenue_growth=-0.05),  # -5%
    ]
    scores = score_category("growth", stocks)
    assert scores["A"].score == 5
    assert scores["C"].score == 1
    assert scores["B"].score == 3


def test_missing_data_gets_neutral_3():
    stocks = [
        _metrics("A", forward_pe=10.0),
        _metrics("B", forward_pe=None),
        _metrics("C", forward_pe=30.0),
    ]
    scores = score_category("valuation", stocks)
    assert scores["A"].score == 5
    assert scores["C"].score == 1
    assert scores["B"].score == 3
    assert scores["B"].display == "— no data"


def test_all_missing_all_neutral():
    stocks = [
        _metrics("A", forward_pe=None),
        _metrics("B", forward_pe=None),
    ]
    scores = score_category("valuation", stocks)
    assert scores["A"].score == 3
    assert scores["B"].score == 3


def test_single_stock_gets_5():
    stocks = [_metrics("A", forward_pe=15.0)]
    scores = score_category("valuation", stocks)
    assert scores["A"].score == 5


def test_health_lower_debt_equity_better():
    stocks = [
        _metrics("A", debt_to_equity=0.20),
        _metrics("B", debt_to_equity=0.80),
        _metrics("C", debt_to_equity=1.50),
    ]
    scores = score_category("health", stocks)
    assert scores["A"].score == 5
    assert scores["C"].score == 1


def test_compute_weighted_scores_ranks_best_first():
    # A dominates valuation and growth; B is mediocre; C is worst everywhere
    stocks = [
        _metrics("A", forward_pe=10.0, revenue_growth=0.30, operating_margin=0.20,
                 roe=0.30, debt_to_equity=0.20, dividend_yield=0.03),
        _metrics("B", forward_pe=20.0, revenue_growth=0.10, operating_margin=0.10,
                 roe=0.15, debt_to_equity=0.80, dividend_yield=0.02),
        _metrics("C", forward_pe=30.0, revenue_growth=-0.05, operating_margin=0.02,
                 roe=0.05, debt_to_equity=1.50, dividend_yield=0.01),
    ]
    rankings = compute_weighted_scores(stocks, DEFAULT_WEIGHTS)
    assert rankings[0].ticker == "A"
    assert rankings[0].rank == 1
    assert rankings[-1].ticker == "C"
    assert rankings[-1].rank == 3


def test_compute_weighted_scores_weights_change_order():
    # A has better valuation; B has better growth.
    stocks = [
        _metrics("A", forward_pe=5.0, revenue_growth=0.05,
                 operating_margin=0.10, roe=0.10, debt_to_equity=0.50, dividend_yield=0.02),
        _metrics("B", forward_pe=50.0, revenue_growth=0.50,
                 operating_margin=0.10, roe=0.10, debt_to_equity=0.50, dividend_yield=0.02),
    ]
    # Weight valuation heavily → A wins
    val_heavy = {"valuation": 1.0, "growth": 0.0, "profitability": 0.0,
                 "roic": 0.0, "health": 0.0, "dividend": 0.0}
    rankings_val = compute_weighted_scores(stocks, val_heavy)
    assert rankings_val[0].ticker == "A"

    # Weight growth heavily → B wins
    growth_heavy = {"valuation": 0.0, "growth": 1.0, "profitability": 0.0,
                    "roic": 0.0, "health": 0.0, "dividend": 0.0}
    rankings_growth = compute_weighted_scores(stocks, growth_heavy)
    assert rankings_growth[0].ticker == "B"


def test_ties_broken_alphabetically():
    # Identical metrics → same weighted score → alphabetical tie-break
    stocks = [
        _metrics("Z", forward_pe=10.0, revenue_growth=0.10, operating_margin=0.10,
                 roe=0.10, debt_to_equity=0.50, dividend_yield=0.02),
        _metrics("A", forward_pe=10.0, revenue_growth=0.10, operating_margin=0.10,
                 roe=0.10, debt_to_equity=0.50, dividend_yield=0.02),
    ]
    rankings = compute_weighted_scores(stocks, DEFAULT_WEIGHTS)
    # Both have equal weighted_score; A comes first alphabetically
    assert rankings[0].ticker == "A"
    assert rankings[1].ticker == "Z"


def test_weights_are_normalized_if_not_sum_to_one():
    stocks = [
        _metrics("A", forward_pe=10.0, revenue_growth=0.10, operating_margin=0.10,
                 roe=0.10, debt_to_equity=0.50, dividend_yield=0.02),
        _metrics("B", forward_pe=30.0, revenue_growth=0.05, operating_margin=0.05,
                 roe=0.05, debt_to_equity=1.00, dividend_yield=0.01),
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
