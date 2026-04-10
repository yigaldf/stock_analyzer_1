from app.models.schemas import CategoryScore, StockInfo, StockMetrics, StockRanking


def test_stock_info_roundtrip():
    info = StockInfo(
        ticker="LULU",
        name="Lululemon Athletica",
        sector="Consumer Cyclical",
        current_price=342.10,
    )
    assert info.ticker == "LULU"
    assert info.current_price == 342.10


def test_stock_metrics_allows_none():
    m = StockMetrics(
        ticker="LULU",
        forward_pe=13.0,
        trailing_pe=None,
        peg_ratio=None,
        price_to_sales=None,
        market_cap=None,
        profit_margin=None,
        operating_margin=None,
        revenue_growth=None,
        eps_growth=None,
        roe=None,
        debt_to_equity=None,
        beta=None,
        dividend_yield=None,
    )
    assert m.forward_pe == 13.0
    assert m.trailing_pe is None


def test_category_score_fields():
    score = CategoryScore(
        category="valuation",
        score=5,
        raw_value=13.0,
        display="13.0x fwd P/E",
    )
    assert score.score == 5
    assert score.category == "valuation"


def test_stock_ranking_fields():
    ranking = StockRanking(
        ticker="LULU",
        category_scores=[],
        weighted_score=3.8,
        rank=2,
    )
    assert ranking.rank == 2
    assert ranking.weighted_score == 3.8
