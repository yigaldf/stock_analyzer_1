from app.models.schemas import (
    CategoryScore,
    QuarterlyValuation,
    StockInfo,
    StockMetrics,
    StockRanking,
)


def test_stock_info_roundtrip():
    info = StockInfo(
        ticker="LULU",
        name="Lululemon Athletica",
        sector="Consumer Cyclical",
        current_price=342.10,
        market_cap=58_000_000_000,
    )
    assert info.ticker == "LULU"
    assert info.current_price == 342.10
    assert info.market_cap == 58_000_000_000


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
        revenue_growth_yoy=None,
        earnings_growth_yoy=None,
        roe=None,
        debt_to_equity=None,
        beta=None,
        forward_dividend_yield=None,
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


def test_quarterly_valuation_roundtrip():
    q = QuarterlyValuation(
        period="Current",
        market_cap=1_810_000_000.0,
        enterprise_value=2_000_000_000.0,
        trailing_pe=18.5,
        forward_pe=13.0,
        peg_ratio=0.90,
        price_to_sales=5.1,
        price_to_book=4.2,
        ev_to_revenue=4.8,
        ev_to_ebitda=11.3,
    )
    dumped = q.model_dump()
    assert dumped["period"] == "Current"
    assert dumped["forward_pe"] == 13.0
    rebuilt = QuarterlyValuation(**dumped)
    assert rebuilt == q


def test_quarterly_valuation_allows_none_for_all_numerics():
    q = QuarterlyValuation(period="9/30/2025")
    assert q.market_cap is None
    assert q.forward_pe is None


def test_stock_metrics_has_new_fields():
    m = StockMetrics(
        ticker="LULU",
        forward_pe=13.0,
        trailing_pe=18.5,
        peg_ratio=0.90,
        price_to_sales=5.1,
        price_to_book=4.2,
        ev_to_revenue=4.8,
        ev_to_ebitda=11.3,
        market_cap=58_000_000_000.0,
        enterprise_value=60_000_000_000.0,
        profit_margin=0.1422,
        operating_margin=0.199,
        roe=0.31,
        roa=0.18,
        revenue_growth_yoy=0.226,
        earnings_growth_yoy=-0.229,
        debt_to_equity=0.3625,
        current_ratio=2.1,
        total_cash=2_000_000_000.0,
        total_debt=1_500_000_000.0,
        operating_cash_flow=1_700_000_000.0,
        levered_free_cash_flow=1_400_000_000.0,
        beta=1.4,
        forward_dividend_yield=None,
        payout_ratio=None,
    )
    assert m.ticker == "LULU"
    assert m.peg_ratio == 0.90
    assert m.roa == 0.18
    assert m.levered_free_cash_flow == 1_400_000_000.0
    assert m.valuation_history == []  # default empty list


def test_stock_metrics_with_valuation_history():
    history = [
        QuarterlyValuation(period="Current", forward_pe=13.0),
        QuarterlyValuation(period="12/31/2025", forward_pe=15.0),
        QuarterlyValuation(period="9/30/2025", forward_pe=18.0),
    ]
    m = StockMetrics(ticker="LULU", valuation_history=history)
    assert len(m.valuation_history) == 3
    assert m.valuation_history[0].forward_pe == 13.0
    assert m.valuation_history[2].period == "9/30/2025"


def test_stock_metrics_source_defaults_none():
    m = StockMetrics(ticker="LULU")
    assert m.source is None


def test_stock_metrics_source_accepts_httpx():
    m = StockMetrics(ticker="LULU", source="httpx")
    assert m.source == "httpx"


def test_stock_metrics_source_accepts_playwright():
    m = StockMetrics(ticker="LULU", source="playwright")
    assert m.source == "playwright"
