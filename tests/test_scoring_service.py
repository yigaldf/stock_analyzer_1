from app.models.schemas import StockMetrics
from app.services.scoring_service import score_category


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
