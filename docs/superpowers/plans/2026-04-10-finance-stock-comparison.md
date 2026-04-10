# Finance Stock Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 4-step Streamlit wizard that lets a user select a stock, pick up to 7 competitors, compare 12 financial metrics, and get a user-weighted ranking with an AI-generated recommendation.

**Architecture:** Three-layer: Streamlit UI → pure Python services (stock data + scoring) → Agno agents (peer discovery + recommendation). Services are Streamlit-independent and fully unit-tested. AI output is validated; the app works even when the LLM fails.

**Tech Stack:** Python 3.12, Streamlit, yfinance, Agno, Pydantic, pytest, ruff, uv.

**Spec:** [docs/superpowers/specs/2026-04-10-finance-stock-comparison-design.md](../specs/2026-04-10-finance-stock-comparison-design.md)

---

## Task 1: Add dependencies and project skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `app/ui/__init__.py`
- Create: `app/ui/screens/__init__.py`

- [ ] **Step 1: Add streamlit and yfinance to pyproject.toml**

Replace the `dependencies` block in `pyproject.toml`:

```toml
[project]
name = "stock-analyzer"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "agno>=2.5.14",
    "fastapi>=0.135.3",
    "pytest>=9.0.3",
    "ruff>=0.15.9",
    "uvicorn>=0.44.0",
    "streamlit>=1.40.0",
    "yfinance>=0.2.50",
    "pydantic>=2.0.0",
]
```

- [ ] **Step 2: Install the new dependencies**

Run: `uv sync`
Expected: lockfile updated, streamlit and yfinance installed, no errors.

- [ ] **Step 3: Create empty `__init__.py` files for new UI packages**

Create `app/ui/__init__.py` with content:
```python
```

Create `app/ui/screens/__init__.py` with content:
```python
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock app/ui/__init__.py app/ui/screens/__init__.py
git commit -m "chore: add streamlit, yfinance, pydantic deps and ui package"
```

---

## Task 2: Pydantic data models

**Files:**
- Create: `app/models/schemas.py`
- Test: `tests/test_schemas.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_schemas.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.schemas'`.

- [ ] **Step 3: Write the implementation**

Create `app/models/schemas.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: 4 passing tests.

- [ ] **Step 5: Commit**

```bash
git add app/models/schemas.py tests/test_schemas.py
git commit -m "feat: add pydantic schemas for stock data and rankings"
```

---

## Task 3: scoring_service — score_category (lower-is-better)

**Files:**
- Create: `app/services/scoring_service.py`
- Test: `tests/test_scoring_service.py`

- [ ] **Step 1: Write the failing test for valuation (lower P/E is better)**

Create `tests/test_scoring_service.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scoring_service.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `app/services/scoring_service.py`:

```python
from app.models.schemas import CategoryScore, StockMetrics

CATEGORIES = ["valuation", "growth", "profitability", "roic", "health", "dividend"]

DEFAULT_WEIGHTS: dict[str, float] = {
    "valuation": 0.20,
    "growth": 0.20,
    "profitability": 0.20,
    "roic": 0.15,
    "health": 0.15,
    "dividend": 0.10,
}

# Primary metric used to score each category, with direction
# direction = "lower" means lower raw value = better score
_CATEGORY_CONFIG: dict[str, dict] = {
    "valuation": {"field": "forward_pe", "direction": "lower", "label": "fwd P/E"},
    "growth": {"field": "revenue_growth", "direction": "higher", "label": "rev growth"},
    "profitability": {"field": "operating_margin", "direction": "higher", "label": "op margin"},
    "roic": {"field": "roe", "direction": "higher", "label": "ROE"},
    "health": {"field": "debt_to_equity", "direction": "lower", "label": "D/E"},
    "dividend": {"field": "dividend_yield", "direction": "higher", "label": "div yield"},
}


def _format_display(category: str, raw: float | None) -> str:
    if raw is None:
        return "— no data"
    label = _CATEGORY_CONFIG[category]["label"]
    if category in ("valuation",):
        return f"{raw:.1f}x {label}"
    if category in ("growth", "profitability", "dividend"):
        return f"{raw * 100:.1f}% {label}"
    if category == "roic":
        return f"{raw * 100:.1f}% {label}"
    if category == "health":
        return f"{raw:.2f} {label}"
    return f"{raw} {label}"


def score_category(
    category: str,
    stocks_metrics: list[StockMetrics],
) -> dict[str, CategoryScore]:
    """Score each stock 1-5 for one category via relative ranking within the peer group."""
    config = _CATEGORY_CONFIG[category]
    field = config["field"]
    direction = config["direction"]

    values: list[tuple[str, float]] = []
    missing: list[str] = []
    for stock in stocks_metrics:
        raw = getattr(stock, field)
        if raw is None:
            missing.append(stock.ticker)
        else:
            values.append((stock.ticker, float(raw)))

    result: dict[str, CategoryScore] = {}

    if len(values) == 0:
        # Everyone is missing — everyone is neutral
        for stock in stocks_metrics:
            result[stock.ticker] = CategoryScore(
                category=category,
                score=3,
                raw_value=None,
                display="— no data",
            )
        return result

    if len(values) == 1:
        only_ticker, only_raw = values[0]
        result[only_ticker] = CategoryScore(
            category=category,
            score=5,
            raw_value=only_raw,
            display=_format_display(category, only_raw),
        )
    else:
        reverse = direction == "higher"
        sorted_values = sorted(values, key=lambda x: x[1], reverse=reverse)
        n = len(sorted_values)
        # Best gets 5, worst gets 1, linear interpolation (integer scores 1-5)
        for idx, (ticker, raw) in enumerate(sorted_values):
            if n == 1:
                score = 5
            else:
                # position 0 (best) → 5, position n-1 (worst) → 1
                score_float = 5 - (4 * idx / (n - 1))
                score = round(score_float)
            result[ticker] = CategoryScore(
                category=category,
                score=score,
                raw_value=raw,
                display=_format_display(category, raw),
            )

    for ticker in missing:
        result[ticker] = CategoryScore(
            category=category,
            score=3,
            raw_value=None,
            display="— no data",
        )

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scoring_service.py -v`
Expected: 1 passing test.

- [ ] **Step 5: Commit**

```bash
git add app/services/scoring_service.py tests/test_scoring_service.py
git commit -m "feat: score_category with relative 1-5 ranking (lower-is-better)"
```

---

## Task 4: scoring_service — higher-is-better and missing data

**Files:**
- Test: `tests/test_scoring_service.py` (modify)

- [ ] **Step 1: Append more tests**

Append to `tests/test_scoring_service.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify all pass**

Run: `uv run pytest tests/test_scoring_service.py -v`
Expected: 6 passing tests.

- [ ] **Step 3: Commit**

```bash
git add tests/test_scoring_service.py
git commit -m "test: cover higher-is-better, missing data, single stock, health direction"
```

---

## Task 5: scoring_service — compute_weighted_scores

**Files:**
- Modify: `app/services/scoring_service.py`
- Modify: `tests/test_scoring_service.py`

- [ ] **Step 1: Write failing test for weighted scoring pipeline**

Append to `tests/test_scoring_service.py`:

```python
from app.services.scoring_service import DEFAULT_WEIGHTS, compute_weighted_scores


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scoring_service.py -v`
Expected: 4 new failures with `ImportError: cannot import name 'compute_weighted_scores'`.

- [ ] **Step 3: Implement compute_weighted_scores**

Append to `app/services/scoring_service.py`:

```python
from app.models.schemas import StockRanking


def compute_weighted_scores(
    stocks: list[StockMetrics],
    weights: dict[str, float],
) -> list[StockRanking]:
    """Full pipeline: score all categories → apply weights → sort → assign ranks.

    Weights are normalized internally so they always sum to 1.0.
    """
    # Normalize weights
    total = sum(weights.get(cat, 0.0) for cat in CATEGORIES)
    if total <= 0:
        raise ValueError("At least one category weight must be positive.")
    norm = {cat: weights.get(cat, 0.0) / total for cat in CATEGORIES}

    # Score each category
    per_category: dict[str, dict[str, CategoryScore]] = {}
    for cat in CATEGORIES:
        per_category[cat] = score_category(cat, stocks)

    # Assemble per-stock rankings
    rankings: list[StockRanking] = []
    for stock in stocks:
        category_scores = [per_category[cat][stock.ticker] for cat in CATEGORIES]
        weighted = sum(
            cs.score * norm[cs.category] for cs in category_scores
        )
        rankings.append(
            StockRanking(
                ticker=stock.ticker,
                category_scores=category_scores,
                weighted_score=round(weighted, 4),
                rank=0,  # filled in below
            )
        )

    # Sort: weighted_score desc, then ticker asc (alphabetical tie-break)
    rankings.sort(key=lambda r: (-r.weighted_score, r.ticker))
    for idx, r in enumerate(rankings, start=1):
        r.rank = idx

    return rankings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scoring_service.py -v`
Expected: 10 passing tests total.

- [ ] **Step 5: Commit**

```bash
git add app/services/scoring_service.py tests/test_scoring_service.py
git commit -m "feat: compute_weighted_scores pipeline with normalization and tie-breaking"
```

---

## Task 6: stock_service — validate_tickers

**Files:**
- Create: `app/services/stock_service.py`
- Create: `tests/test_stock_service.py`

- [ ] **Step 1: Write failing test with mocked yfinance**

Create `tests/test_stock_service.py`:

```python
from unittest.mock import MagicMock, patch

from app.services.stock_service import (
    get_stock_info,
    get_stock_metrics,
    validate_tickers,
)


@patch("app.services.stock_service.yf.Ticker")
def test_validate_tickers_drops_invalid(mock_ticker):
    def side_effect(t):
        mock = MagicMock()
        if t == "LULU":
            mock.info = {"symbol": "LULU", "longName": "Lululemon"}
        elif t == "NKE":
            mock.info = {"symbol": "NKE", "longName": "Nike"}
        else:
            mock.info = {}  # yfinance returns near-empty dict for invalid
        return mock

    mock_ticker.side_effect = side_effect
    result = validate_tickers(["LULU", "BOGUS", "NKE"])
    assert "LULU" in result
    assert "NKE" in result
    assert "BOGUS" not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stock_service.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `app/services/stock_service.py`:

```python
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import yfinance as yf

from app.models.schemas import StockInfo, StockMetrics


def _is_valid_info(info: dict | None) -> bool:
    """A ticker is valid if yfinance returns a dict with a longName or shortName."""
    if not info:
        return False
    return bool(info.get("longName") or info.get("shortName"))


def validate_tickers(tickers: list[str]) -> list[str]:
    """Return only the tickers that yfinance recognizes. Runs in parallel."""

    def _check(t: str) -> str | None:
        try:
            info = yf.Ticker(t).info
            return t if _is_valid_info(info) else None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(_check, tickers))

    return [t for t in results if t is not None]


def get_stock_info(ticker: str) -> StockInfo | None:
    """Fetch basic info for one ticker."""
    try:
        info = yf.Ticker(ticker).info
    except Exception:
        return None
    if not _is_valid_info(info):
        return None

    name = info.get("longName") or info.get("shortName") or ticker
    sector = info.get("sector") or "Unknown"
    price = info.get("currentPrice") or info.get("regularMarketPrice") or 0.0
    return StockInfo(
        ticker=ticker,
        name=name,
        sector=sector,
        current_price=float(price),
    )


def get_stock_metrics(ticker: str) -> StockMetrics | None:
    """Fetch all 12 scoring metrics + market_cap for one ticker."""
    try:
        info = yf.Ticker(ticker).info
    except Exception:
        return None
    if not _is_valid_info(info):
        return None

    def _get(key: str) -> float | None:
        v = info.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return StockMetrics(
        ticker=ticker,
        forward_pe=_get("forwardPE"),
        trailing_pe=_get("trailingPE"),
        peg_ratio=_get("pegRatio"),
        price_to_sales=_get("priceToSalesTrailing12Months"),
        market_cap=_get("marketCap"),
        profit_margin=_get("profitMargins"),
        operating_margin=_get("operatingMargins"),
        revenue_growth=_get("revenueGrowth"),
        eps_growth=_get("earningsGrowth"),
        roe=_get("returnOnEquity"),
        debt_to_equity=(
            _get("debtToEquity") / 100 if _get("debtToEquity") is not None else None
        ),
        beta=_get("beta"),
        dividend_yield=_get("dividendYield"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stock_service.py -v`
Expected: 1 passing test.

- [ ] **Step 5: Commit**

```bash
git add app/services/stock_service.py tests/test_stock_service.py
git commit -m "feat: stock_service with validate_tickers, get_stock_info, get_stock_metrics"
```

---

## Task 7: stock_service — tests for get_stock_info and get_stock_metrics

**Files:**
- Modify: `tests/test_stock_service.py`

- [ ] **Step 1: Append more tests**

Append to `tests/test_stock_service.py`:

```python
@patch("app.services.stock_service.yf.Ticker")
def test_get_stock_info_valid_ticker(mock_ticker):
    mock_ticker.return_value.info = {
        "longName": "Lululemon Athletica Inc.",
        "sector": "Consumer Cyclical",
        "currentPrice": 342.10,
    }
    info = get_stock_info("LULU")
    assert info is not None
    assert info.ticker == "LULU"
    assert info.name == "Lululemon Athletica Inc."
    assert info.sector == "Consumer Cyclical"
    assert info.current_price == 342.10


@patch("app.services.stock_service.yf.Ticker")
def test_get_stock_info_invalid_ticker_returns_none(mock_ticker):
    mock_ticker.return_value.info = {}
    assert get_stock_info("BOGUS") is None


@patch("app.services.stock_service.yf.Ticker")
def test_get_stock_info_on_exception_returns_none(mock_ticker):
    mock_ticker.side_effect = RuntimeError("network error")
    assert get_stock_info("LULU") is None


@patch("app.services.stock_service.yf.Ticker")
def test_get_stock_metrics_populates_fields(mock_ticker):
    mock_ticker.return_value.info = {
        "longName": "Lululemon",
        "forwardPE": 13.0,
        "trailingPE": 18.5,
        "pegRatio": 1.2,
        "priceToSalesTrailing12Months": 5.1,
        "marketCap": 58000000000,
        "profitMargins": 0.15,
        "operatingMargins": 0.199,
        "revenueGrowth": 0.05,
        "earningsGrowth": 0.08,
        "returnOnEquity": 0.31,
        "debtToEquity": 36.0,  # yfinance returns raw percent
        "beta": 1.4,
        "dividendYield": None,
    }
    m = get_stock_metrics("LULU")
    assert m is not None
    assert m.forward_pe == 13.0
    assert m.operating_margin == 0.199
    assert m.roe == 0.31
    # debt_to_equity is divided by 100
    assert m.debt_to_equity == 0.36
    assert m.dividend_yield is None


@patch("app.services.stock_service.yf.Ticker")
def test_get_stock_metrics_missing_fields_become_none(mock_ticker):
    mock_ticker.return_value.info = {
        "longName": "Tiny Inc",
        "forwardPE": 20.0,
        # everything else missing
    }
    m = get_stock_metrics("TINY")
    assert m is not None
    assert m.forward_pe == 20.0
    assert m.trailing_pe is None
    assert m.market_cap is None
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_stock_service.py -v`
Expected: 6 passing tests total.

- [ ] **Step 3: Commit**

```bash
git add tests/test_stock_service.py
git commit -m "test: cover stock_service success, invalid, exception, missing fields"
```

---

## Task 8: peers_agent — Agno peer discovery with fallback

**Files:**
- Create: `app/agents/peers_agent.py`
- Create: `tests/test_peers_agent.py`

- [ ] **Step 1: Write failing test with mocked Agno**

Create `tests/test_peers_agent.py`:

```python
from unittest.mock import MagicMock, patch

from app.agents.peers_agent import suggest_peers


@patch("app.agents.peers_agent._run_agent")
def test_suggest_peers_parses_json(mock_run):
    mock_run.return_value = '{"tickers": ["NKE", "ADDYY", "ONON", "UA"]}'
    result = suggest_peers("LULU", "Lululemon", "Consumer Cyclical")
    assert result == ["NKE", "ADDYY", "ONON", "UA"]


@patch("app.agents.peers_agent._run_agent")
def test_suggest_peers_handles_wrapped_json(mock_run):
    # LLMs sometimes wrap JSON in prose
    mock_run.return_value = (
        "Here are the competitors:\n"
        '```json\n{"tickers": ["NKE", "ADDYY"]}\n```\n'
        "Hope this helps!"
    )
    result = suggest_peers("LULU", "Lululemon", "Consumer Cyclical")
    assert "NKE" in result
    assert "ADDYY" in result


@patch("app.agents.peers_agent._run_agent")
def test_suggest_peers_returns_empty_on_garbage(mock_run):
    mock_run.return_value = "I don't know, try Google"
    result = suggest_peers("LULU", "Lululemon", "Consumer Cyclical")
    assert result == []


@patch("app.agents.peers_agent._run_agent")
def test_suggest_peers_returns_empty_on_exception(mock_run):
    mock_run.side_effect = RuntimeError("no api key")
    result = suggest_peers("LULU", "Lululemon", "Consumer Cyclical")
    assert result == []


@patch("app.agents.peers_agent._run_agent")
def test_suggest_peers_caps_at_10(mock_run):
    mock_run.return_value = (
        '{"tickers": ["A","B","C","D","E","F","G","H","I","J","K","L"]}'
    )
    result = suggest_peers("LULU", "Lululemon", "Consumer Cyclical")
    assert len(result) == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_peers_agent.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement peers_agent**

Create `app/agents/peers_agent.py`:

```python
from __future__ import annotations

import json
import re


def _run_agent(prompt: str) -> str:
    """Run the Agno agent and return its raw text response.

    Isolated so tests can patch it without initializing Agno.
    """
    # Lazy import so tests don't need Agno configured
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat

    agent = Agent(
        model=OpenAIChat(id="gpt-4o-mini"),
        instructions=(
            "You are a financial research assistant. Given a stock, "
            "return up to 10 publicly traded US competitors as JSON in the "
            'form {"tickers": ["TICKER1", "TICKER2", ...]}. '
            "Only return real tickers on major US exchanges. "
            "Return ONLY the JSON object, no prose."
        ),
    )
    response = agent.run(prompt)
    return str(response.content) if hasattr(response, "content") else str(response)


_JSON_BLOCK_RE = re.compile(r"\{[^{}]*\"tickers\"[^{}]*\}", re.DOTALL)


def _extract_tickers(raw: str) -> list[str]:
    # Try direct parse first
    try:
        parsed = json.loads(raw)
        tickers = parsed.get("tickers", [])
        if isinstance(tickers, list):
            return [str(t).upper() for t in tickers]
    except (json.JSONDecodeError, AttributeError):
        pass

    # Fall back to regex-extract the first {...} block containing "tickers"
    match = _JSON_BLOCK_RE.search(raw)
    if match:
        try:
            parsed = json.loads(match.group(0))
            tickers = parsed.get("tickers", [])
            if isinstance(tickers, list):
                return [str(t).upper() for t in tickers]
        except json.JSONDecodeError:
            return []

    return []


def suggest_peers(ticker: str, name: str, sector: str) -> list[str]:
    """Ask the AI agent for up to 10 competitor tickers. Empty list on any failure."""
    prompt = (
        f"Find up to 10 publicly traded US competitors for {ticker} "
        f"({name}, sector: {sector}). "
        'Respond ONLY with JSON: {"tickers": ["TICKER1", "TICKER2", ...]}'
    )
    try:
        raw = _run_agent(prompt)
    except Exception:
        return []

    tickers = _extract_tickers(raw)
    # Remove the source ticker if the agent included it
    tickers = [t for t in tickers if t != ticker.upper()]
    return tickers[:10]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_peers_agent.py -v`
Expected: 5 passing tests.

- [ ] **Step 5: Commit**

```bash
git add app/agents/peers_agent.py tests/test_peers_agent.py
git commit -m "feat: peers_agent with JSON parsing, fallback, and 10-ticker cap"
```

---

## Task 9: recommendation_agent — narrative generation with fallback

**Files:**
- Create: `app/agents/recommendation_agent.py`
- Create: `tests/test_recommendation_agent.py`

- [ ] **Step 1: Write failing tests with mocked Agno**

Create `tests/test_recommendation_agent.py`:

```python
from unittest.mock import patch

from app.agents.recommendation_agent import generate_recommendation
from app.models.schemas import CategoryScore, StockRanking


def _ranking(ticker: str, weighted: float, rank: int) -> StockRanking:
    return StockRanking(
        ticker=ticker,
        category_scores=[
            CategoryScore(category="valuation", score=5, raw_value=13.0, display="13x fwd P/E"),
            CategoryScore(category="growth", score=5, raw_value=0.30, display="30% rev growth"),
            CategoryScore(category="profitability", score=4, raw_value=0.15, display="15% op margin"),
            CategoryScore(category="roic", score=5, raw_value=0.30, display="30% ROE"),
            CategoryScore(category="health", score=5, raw_value=0.20, display="0.20 D/E"),
            CategoryScore(category="dividend", score=1, raw_value=None, display="— no data"),
        ],
        weighted_score=weighted,
        rank=rank,
    )


@patch("app.agents.recommendation_agent._run_agent")
def test_generate_recommendation_returns_agent_text(mock_run):
    mock_run.return_value = "Top pick is ONON due to its strong growth of 30% YoY."
    rankings = [_ranking("ONON", 4.0, 1), _ranking("LULU", 3.8, 2)]
    weights = {"valuation": 0.2, "growth": 0.2, "profitability": 0.2,
               "roic": 0.15, "health": 0.15, "dividend": 0.10}
    result = generate_recommendation(rankings, weights)
    assert "ONON" in result
    mock_run.assert_called_once()


@patch("app.agents.recommendation_agent._run_agent")
def test_generate_recommendation_fallback_on_exception(mock_run):
    mock_run.side_effect = RuntimeError("no api key")
    rankings = [_ranking("ONON", 4.0, 1), _ranking("LULU", 3.8, 2)]
    weights = {"valuation": 0.2, "growth": 0.2, "profitability": 0.2,
               "roic": 0.15, "health": 0.15, "dividend": 0.10}
    result = generate_recommendation(rankings, weights)
    assert "ONON" in result
    assert "4.00" in result or "4.0" in result


def test_generate_recommendation_empty_rankings_returns_message():
    result = generate_recommendation([], {})
    assert result == "No stocks to rank."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_recommendation_agent.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement recommendation_agent**

Create `app/agents/recommendation_agent.py`:

```python
from __future__ import annotations

from app.models.schemas import StockRanking


def _run_agent(prompt: str) -> str:
    """Run the Agno agent and return its raw text response.

    Isolated so tests can patch it without initializing Agno.
    """
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat

    agent = Agent(
        model=OpenAIChat(id="gpt-4o-mini"),
        instructions=(
            "You are a concise investment analyst. Given a ranking and user weights, "
            "write a 2-3 sentence recommendation explaining why the top stock stands out. "
            "Reference specific metrics. Do NOT give financial advice disclaimers."
        ),
    )
    response = agent.run(prompt)
    return str(response.content) if hasattr(response, "content") else str(response)


def _fallback_summary(rankings: list[StockRanking]) -> str:
    top = rankings[0]
    return (
        f"Top pick: {top.ticker} with weighted score {top.weighted_score:.2f}. "
        f"(AI recommendation unavailable.)"
    )


def _format_prompt(rankings: list[StockRanking], weights: dict[str, float]) -> str:
    top = rankings[0]
    runners = rankings[1:3]
    lines = [
        f"User weights: " + ", ".join(
            f"{k}={v*100:.0f}%" for k, v in weights.items()
        ),
        "",
        f"Top pick: {top.ticker} (weighted score {top.weighted_score:.2f})",
    ]
    for cs in top.category_scores:
        lines.append(f"  - {cs.category}: {cs.score}/5 ({cs.display})")
    if runners:
        lines.append("")
        lines.append("Runners up:")
        for r in runners:
            lines.append(f"  - {r.ticker}: {r.weighted_score:.2f}")
    lines.append("")
    lines.append(
        "Write a 2-3 sentence recommendation explaining why the top pick stands out "
        "given these weights. Reference specific metric values."
    )
    return "\n".join(lines)


def generate_recommendation(
    rankings: list[StockRanking],
    weights: dict[str, float],
) -> str:
    """Generate an AI recommendation for the top pick. Falls back to a deterministic
    summary on any error or if the top pick is empty."""
    if not rankings:
        return "No stocks to rank."

    prompt = _format_prompt(rankings, weights)
    try:
        return _run_agent(prompt).strip()
    except Exception:
        return _fallback_summary(rankings)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_recommendation_agent.py -v`
Expected: 3 passing tests.

- [ ] **Step 5: Commit**

```bash
git add app/agents/recommendation_agent.py tests/test_recommendation_agent.py
git commit -m "feat: recommendation_agent with deterministic fallback summary"
```

---

## Task 10: UI session state helpers

**Files:**
- Create: `app/ui/state.py`

- [ ] **Step 1: Create the session state helper module**

Create `app/ui/state.py`:

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add app/ui/state.py
git commit -m "feat: session state helpers for wizard"
```

---

## Task 11: UI navigation component (progress bar + back/next)

**Files:**
- Create: `app/ui/nav.py`

- [ ] **Step 1: Create the nav helper**

Create `app/ui/nav.py`:

```python
"""Wizard progress indicator and back/next button bar."""
from __future__ import annotations

import streamlit as st

from app.ui import state

STEP_LABELS = ["Select Stock", "Pick Competitors", "Compare Metrics", "Rank & Recommend"]


def progress_header(current_step: int) -> None:
    st.markdown(f"### Step {current_step} of 4 — {STEP_LABELS[current_step - 1]}")
    st.progress(current_step / 4)


def nav_buttons(
    current_step: int,
    *,
    next_enabled: bool = True,
    next_label: str = "Next →",
) -> None:
    """Render Back/Next buttons at the bottom of a screen."""
    col_back, col_spacer, col_next = st.columns([1, 3, 1])
    with col_back:
        if current_step > 1:
            if st.button("← Back", key=f"back_{current_step}"):
                state.goto_step(current_step - 1)
                st.rerun()
    with col_next:
        if current_step < 4:
            if st.button(
                next_label,
                key=f"next_{current_step}",
                disabled=not next_enabled,
            ):
                state.goto_step(current_step + 1)
                st.rerun()
```

- [ ] **Step 2: Commit**

```bash
git add app/ui/nav.py
git commit -m "feat: wizard navigation (progress header + back/next buttons)"
```

---

## Task 12: Screen 1 — Select a stock

**Files:**
- Create: `app/ui/screens/step1_select.py`

- [ ] **Step 1: Implement the select-stock screen**

Create `app/ui/screens/step1_select.py`:

```python
from __future__ import annotations

import streamlit as st

from app.services.stock_service import get_stock_info
from app.ui import nav, state


def render() -> None:
    nav.progress_header(1)
    st.write("Enter a stock ticker to begin.")

    ticker_input = st.text_input(
        "Ticker symbol",
        value=st.session_state.get(state.TICKER) or "",
        placeholder="e.g. LULU",
        key="step1_ticker_input",
    ).upper().strip()

    info = None
    if ticker_input:
        with st.spinner(f"Looking up {ticker_input}..."):
            info = get_stock_info(ticker_input)

        if info is None:
            st.error(f"Ticker '{ticker_input}' not found. Try another symbol.")
        else:
            state.set_ticker(ticker_input, info)
            st.success(f"Found: **{info.name}**")
            col1, col2 = st.columns(2)
            col1.metric("Sector", info.sector)
            col2.metric("Current price", f"${info.current_price:,.2f}")

    nav.nav_buttons(1, next_enabled=info is not None)
```

- [ ] **Step 2: Commit**

```bash
git add app/ui/screens/step1_select.py
git commit -m "feat: wizard step 1 — select a stock"
```

---

## Task 13: Screen 2 — Pick competitors

**Files:**
- Create: `app/ui/screens/step2_peers.py`

- [ ] **Step 1: Implement the peer-selection screen**

Create `app/ui/screens/step2_peers.py`:

```python
from __future__ import annotations

import streamlit as st

from app.agents.peers_agent import suggest_peers
from app.services.stock_service import get_stock_info, validate_tickers
from app.ui import nav, state


def _load_candidates() -> None:
    """Call the peer agent and populate candidates if not already loaded."""
    if st.session_state.get(state.PEER_CANDIDATES):
        return
    info = st.session_state.get(state.STOCK_INFO)
    if info is None:
        return
    with st.spinner("Finding competitors..."):
        raw = suggest_peers(info.ticker, info.name, info.sector)
        validated = validate_tickers(raw) if raw else []
    state.set_peer_candidates(validated)


def render() -> None:
    nav.progress_header(2)
    info = st.session_state.get(state.STOCK_INFO)
    if info is None:
        st.warning("Please select a stock first.")
        nav.nav_buttons(2, next_enabled=False)
        return

    st.write(
        f"AI-suggested competitors for **{info.ticker}** ({info.name}). "
        "Select between 1 and 7."
    )

    _load_candidates()
    candidates: list[str] = st.session_state.get(state.PEER_CANDIDATES, [])

    if not candidates:
        st.warning(
            "Couldn't suggest competitors automatically. "
            "Enter them manually below (comma-separated)."
        )
        manual = st.text_input("Tickers", key="step2_manual", placeholder="NKE, ADDYY, UA")
        if manual:
            tickers = [t.strip().upper() for t in manual.split(",") if t.strip()]
            with st.spinner("Validating tickers..."):
                candidates = validate_tickers(tickers)
            state.set_peer_candidates(candidates)

    # Checkbox list
    selected = list(st.session_state.get(state.SELECTED_PEERS, []))
    if candidates:
        st.write("")
        new_selected: list[str] = []
        cols = st.columns(2)
        for i, t in enumerate(candidates):
            with cols[i % 2]:
                checked = st.checkbox(
                    t,
                    value=(t in selected),
                    key=f"peer_cb_{t}",
                )
                if checked:
                    new_selected.append(t)
        selected = new_selected
        state.set_selected_peers(selected)

    # Validation messages
    next_enabled = False
    if len(selected) == 0:
        if candidates:
            st.info("Select at least 1 competitor to continue.")
    elif len(selected) > 7:
        st.error(f"You selected {len(selected)} competitors. Maximum is 7.")
    else:
        next_enabled = True

    nav.nav_buttons(2, next_enabled=next_enabled)
```

- [ ] **Step 2: Commit**

```bash
git add app/ui/screens/step2_peers.py
git commit -m "feat: wizard step 2 — pick competitors with manual fallback"
```

---

## Task 14: Screen 3 — Metrics comparison table

**Files:**
- Create: `app/ui/screens/step3_metrics.py`

- [ ] **Step 1: Implement the metrics comparison screen**

Create `app/ui/screens/step3_metrics.py`:

```python
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.models.schemas import StockMetrics
from app.services.stock_service import get_stock_metrics
from app.ui import nav, state

# (category label, list of (metric display name, attr, formatter))
_METRIC_ROWS: list[tuple[str, str, callable]] = [
    ("Fwd P/E", "forward_pe", lambda v: f"{v:.1f}x"),
    ("Trailing P/E", "trailing_pe", lambda v: f"{v:.1f}x"),
    ("PEG", "peg_ratio", lambda v: f"{v:.2f}"),
    ("P/S", "price_to_sales", lambda v: f"{v:.1f}"),
    ("Market cap", "market_cap", lambda v: f"${v/1e9:.1f}B"),
    ("Rev growth", "revenue_growth", lambda v: f"{v*100:.1f}%"),
    ("EPS growth", "eps_growth", lambda v: f"{v*100:.1f}%"),
    ("Op margin", "operating_margin", lambda v: f"{v*100:.1f}%"),
    ("Profit margin", "profit_margin", lambda v: f"{v*100:.1f}%"),
    ("ROE", "roe", lambda v: f"{v*100:.1f}%"),
    ("D/E", "debt_to_equity", lambda v: f"{v:.2f}"),
    ("Beta", "beta", lambda v: f"{v:.2f}"),
    ("Div yield", "dividend_yield", lambda v: f"{v*100:.2f}%"),
]


def _format(value: float | None, fmt) -> str:
    if value is None:
        return "—"
    try:
        return fmt(value)
    except Exception:
        return "—"


def _fetch_all_metrics() -> list[str]:
    """Fetch metrics for the selected stock + peers. Returns list of fetch errors."""
    errors: list[str] = []
    all_tickers: list[str] = []
    if st.session_state.get(state.TICKER):
        all_tickers.append(st.session_state[state.TICKER])
    all_tickers.extend(st.session_state.get(state.SELECTED_PEERS, []))

    cache: dict[str, StockMetrics] = st.session_state.get(state.METRICS_CACHE, {})
    for t in all_tickers:
        if t in cache:
            continue
        m = get_stock_metrics(t)
        if m is None:
            errors.append(t)
        else:
            state.cache_metrics(t, m)
    return errors


def render() -> None:
    nav.progress_header(3)
    if not st.session_state.get(state.SELECTED_PEERS):
        st.warning("Please select peers first.")
        nav.nav_buttons(3, next_enabled=False)
        return

    with st.spinner("Fetching financial metrics..."):
        errors = _fetch_all_metrics()
    if errors:
        st.warning(f"Couldn't fetch metrics for: {', '.join(errors)}")

    metrics_list = state.get_all_selected_metrics()
    if not metrics_list:
        st.error("No metrics available.")
        nav.nav_buttons(3, next_enabled=False)
        return

    st.write("Side-by-side comparison of 12 key metrics.")

    # Build a dataframe: rows = metrics, columns = tickers
    data: dict[str, list[str]] = {"Metric": [row[0] for row in _METRIC_ROWS]}
    for m in metrics_list:
        data[m.ticker] = [
            _format(getattr(m, attr), fmt) for _, attr, fmt in _METRIC_ROWS
        ]
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    nav.nav_buttons(3, next_enabled=True)
```

- [ ] **Step 2: Commit**

```bash
git add app/ui/screens/step3_metrics.py
git commit -m "feat: wizard step 3 — metrics comparison table"
```

---

## Task 15: Screen 4 — Ranking, weight sliders, AI recommendation

**Files:**
- Create: `app/ui/screens/step4_ranking.py`

- [ ] **Step 1: Implement the ranking screen**

Create `app/ui/screens/step4_ranking.py`:

```python
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.agents.recommendation_agent import generate_recommendation
from app.services.scoring_service import CATEGORIES, DEFAULT_WEIGHTS, compute_weighted_scores
from app.ui import nav, state

_CATEGORY_LABELS = {
    "valuation": "Valuation (fwd P/E)",
    "growth": "Revenue Growth",
    "profitability": "Profitability (op margin)",
    "roic": "ROIC (ROE)",
    "health": "Financial Health (D/E)",
    "dividend": "Dividend Yield",
}


def _render_weight_sliders() -> dict[str, float]:
    st.markdown("#### Weights")
    current = st.session_state.get(state.WEIGHTS, dict(DEFAULT_WEIGHTS))
    cols = st.columns(3)
    new_weights: dict[str, float] = {}
    for i, cat in enumerate(CATEGORIES):
        with cols[i % 3]:
            pct = st.slider(
                _CATEGORY_LABELS[cat],
                min_value=0,
                max_value=100,
                value=int(round(current.get(cat, 0) * 100)),
                step=5,
                key=f"weight_slider_{cat}",
            )
            new_weights[cat] = pct / 100
    return new_weights


def render() -> None:
    nav.progress_header(4)
    metrics = state.get_all_selected_metrics()
    if not metrics:
        st.warning("No metrics available. Go back and select stocks first.")
        nav.nav_buttons(4, next_enabled=False)
        return

    weights = _render_weight_sliders()
    state.set_weights(weights)

    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:
        st.warning(
            f"Weights total {total*100:.0f}% — adjust to 100% for an exact balance. "
            "Ranking uses normalized weights."
        )

    if sum(weights.values()) <= 0:
        st.error("At least one category must have a non-zero weight.")
        nav.nav_buttons(4)
        return

    rankings = compute_weighted_scores(metrics, weights)

    # Ranking table
    rows = []
    for r in rankings:
        row = {"Rank": f"#{r.rank}", "Ticker": r.ticker, "Weighted Score": f"{r.weighted_score:.2f}"}
        for cs in r.category_scores:
            row[_CATEGORY_LABELS[cs.category]] = f"{cs.score}/5"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Only regenerate narrative when top pick changes
    top_ticker = rankings[0].ticker
    last_top = st.session_state.get(state.LAST_TOP_PICK)
    last_text = st.session_state.get(state.LAST_RECOMMENDATION)
    if last_top != top_ticker or last_text is None:
        with st.spinner("Generating AI recommendation..."):
            narrative = generate_recommendation(rankings, weights)
        st.session_state[state.LAST_TOP_PICK] = top_ticker
        st.session_state[state.LAST_RECOMMENDATION] = narrative
    else:
        narrative = last_text

    st.markdown("### 🤖 AI Recommendation")
    st.info(narrative)

    nav.nav_buttons(4)
```

- [ ] **Step 2: Commit**

```bash
git add app/ui/screens/step4_ranking.py
git commit -m "feat: wizard step 4 — ranking, weight sliders, AI recommendation"
```

---

## Task 16: Streamlit entry point

**Files:**
- Create: `streamlit_app.py`

- [ ] **Step 1: Create the entry point**

Create `streamlit_app.py`:

```python
"""Entry point for the Finance Stock Comparison wizard.

Run with: uv run streamlit run streamlit_app.py
"""
from __future__ import annotations

import streamlit as st

from app.ui import state
from app.ui.screens import step1_select, step2_peers, step3_metrics, step4_ranking


def main() -> None:
    st.set_page_config(
        page_title="Stock Analyzer",
        page_icon="📈",
        layout="wide",
    )
    st.title("📈 Stock Analyzer")
    state.init_state()

    step = st.session_state.get(state.STEP, 1)
    if step == 1:
        step1_select.render()
    elif step == 2:
        step2_peers.render()
    elif step == 3:
        step3_metrics.render()
    elif step == 4:
        step4_ranking.render()
    else:
        st.error(f"Unknown step: {step}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify all tests still pass**

Run: `uv run pytest -v`
Expected: all tests from tasks 2-9 pass (~24 tests).

- [ ] **Step 3: Verify lint passes**

Run: `uv run ruff check .`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add streamlit_app.py
git commit -m "feat: streamlit entry point routing the 4 wizard screens"
```

---

## Task 17: Update CLAUDE.md and .env.example

**Files:**
- Modify: `CLAUDE.md`
- Modify: `.env.example`

- [ ] **Step 1: Update CLAUDE.md**

Replace the `## Commands` section in `CLAUDE.md` with:

```markdown
## Commands
- Install: `uv sync`
- Run app: `uv run streamlit run streamlit_app.py`
- Run tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
```

And replace the `## Project Structure` section with:

```markdown
## Project Structure
- `streamlit_app.py` — Streamlit entry point
- `app/ui/` — Streamlit UI (screens, state, nav)
- `app/ui/screens/` — One file per wizard step
- `app/services/` — Pure-Python business logic (stock data, scoring)
- `app/agents/` — Agno agents (peer discovery, recommendation)
- `app/models/` — Pydantic schemas
- `tests/` — pytest unit tests (no live API/LLM calls)
```

- [ ] **Step 2: Update .env.example**

Replace the contents of `.env.example` with:

```bash
# LLM provider for Agno agents (pick one)
OPENAI_API_KEY=sk-your-key-here
# ANTHROPIC_API_KEY=sk-ant-your-key-here
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md .env.example
git commit -m "docs: update CLAUDE.md and .env.example for streamlit wizard"
```

---

## Task 18: Final verification

**Files:** None.

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -v`
Expected: all tests pass, no failures or errors.

- [ ] **Step 2: Run lint**

Run: `uv run ruff check .`
Expected: no errors.

- [ ] **Step 3: Smoke-test the app manually**

Run: `uv run streamlit run streamlit_app.py`
Then in a browser:
1. Enter `LULU` → see Lululemon info card
2. Click Next → see competitor checkboxes (or manual entry fallback)
3. Select 3-5 competitors → click Next
4. Review metrics table — values should populate, "—" for missing
5. Click Next → see ranking table, move sliders, observe ranking reorder
6. Verify AI recommendation appears (or deterministic fallback if no LLM key)
7. Click Back from each screen → state should persist

Expected: all 7 checks pass.

- [ ] **Step 4: Confirm success criteria from spec**

Walk through the Success Criteria section of `docs/superpowers/specs/2026-04-10-finance-stock-comparison-design.md` and verify each checkbox is satisfied.

---
