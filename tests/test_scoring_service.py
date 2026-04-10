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
