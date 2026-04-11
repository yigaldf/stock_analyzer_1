from pydantic import BaseModel


class StockInfo(BaseModel):
    ticker: str
    name: str
    sector: str
    current_price: float
    market_cap: float | None = None


class QuarterlyValuation(BaseModel):
    """One column from Yahoo's Valuation Measures table.

    `period` is the column header from the Yahoo page: "Current" or a date
    like "12/31/2025".
    """
    period: str
    market_cap: float | None = None
    enterprise_value: float | None = None
    trailing_pe: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    price_to_sales: float | None = None
    price_to_book: float | None = None
    ev_to_revenue: float | None = None
    ev_to_ebitda: float | None = None


class StockMetrics(BaseModel):
    ticker: str

    # Valuation (current snapshot — mirrors the "Current" column in valuation_history)
    forward_pe: float | None = None
    trailing_pe: float | None = None
    peg_ratio: float | None = None
    price_to_sales: float | None = None
    price_to_book: float | None = None
    ev_to_revenue: float | None = None
    ev_to_ebitda: float | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None

    # Profitability
    profit_margin: float | None = None
    operating_margin: float | None = None

    # Capital efficiency
    roe: float | None = None
    roa: float | None = None

    # Growth
    revenue_growth_yoy: float | None = None
    earnings_growth_yoy: float | None = None

    # Financial health
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    total_cash: float | None = None
    total_debt: float | None = None

    # Cash quality
    operating_cash_flow: float | None = None
    levered_free_cash_flow: float | None = None

    # Risk / display
    beta: float | None = None

    # Dividend
    forward_dividend_yield: float | None = None
    payout_ratio: float | None = None

    # Historical trend (5 quarters + "Current" = typically 6 entries)
    valuation_history: list[QuarterlyValuation] = []


class CategoryScore(BaseModel):
    category: str
    score: int
    raw_value: float | None
    display: str


class StockRanking(BaseModel):
    ticker: str
    category_scores: list[CategoryScore]
    weighted_score: float
    rank: int
