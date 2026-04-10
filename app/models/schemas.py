from pydantic import BaseModel


class StockInfo(BaseModel):
    ticker: str
    name: str
    sector: str
    current_price: float


class StockMetrics(BaseModel):
    ticker: str
    forward_pe: float | None
    trailing_pe: float | None
    peg_ratio: float | None
    price_to_sales: float | None
    market_cap: float | None
    profit_margin: float | None
    operating_margin: float | None
    revenue_growth: float | None
    eps_growth: float | None
    roe: float | None
    debt_to_equity: float | None
    beta: float | None
    dividend_yield: float | None


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
