# Finance Stock Comparison App — Design Spec

**Date:** 2026-04-10
**Status:** Approved design, ready for implementation planning
**Project:** stock_analyzer_1

## Summary

A 4-step wizard web app that lets a user select a stock, choose up to 7 competitors, compare 12 financial metrics side-by-side, and get a weighted ranking with an AI-generated recommendation. Built in Python with Streamlit (UI), yfinance (data), and Agno (AI agents).

## Goals

- Help a user quickly compare a stock against its peers on standardized metrics
- Put the user in control of what "best" means via adjustable category weights
- Use AI where it adds value (peer discovery, narrative recommendation) and deterministic code where reliability matters (data fetching, scoring math)
- Keep the logic layer testable and framework-independent

## Non-goals (out of scope for v1)

- User accounts, authentication, saved comparisons
- Historical price charts or trend analysis
- Alerts, watchlists, portfolio tracking
- Mobile-optimized layout
- Non-US stocks or multi-currency support
- FastAPI REST endpoints (scaffolding kept but not wired up)

## Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.12+ | Already in project |
| UI | Streamlit | Fastest path to a 4-screen wizard in pure Python |
| Data source | yfinance | Free, no API key, has all 12 metrics needed |
| AI agents | Agno | Already in project; used for peers + recommendation |
| Testing | pytest | Already in project |
| Lint/format | ruff | Already in project |
| Package manager | uv | Already in project |

## Architecture

Three-layer architecture:

```
┌────────────────────────────────────────────────────────────┐
│                   Streamlit UI (app/ui/)                   │
│   Screen 1 ──► Screen 2 ──► Screen 3 ──► Screen 4          │
└────────────┬──────────────┬─────────────┬──────────────────┘
             │              │             │
             ▼              ▼             ▼
   ┌────────────────────────────────────────────────┐
   │  Service layer (app/services/)                 │
   │  ─ stock_service.py   (yfinance + cache)       │
   │  ─ scoring_service.py (pure scoring math)      │
   └────────────────────────────────────────────────┘
             │              │             │
             ▼              ▼             ▼
   ┌──────────────┐  ┌─────────────┐  ┌─────────────────┐
   │   yfinance   │  │ peers_agent │  │ recommendation  │
   │              │  │   (Agno)    │  │  agent (Agno)   │
   └──────────────┘  └─────────────┘  └─────────────────┘
```

**Key principles:**
- Services contain no Streamlit imports — fully testable in isolation
- Caching lives at the service boundary via `@st.cache_data(ttl=600)`
- All AI agent output is validated before display (ticker validation via yfinance)
- Ranking math is deterministic Python; Agno only generates the narrative explanation
- Wizard state persists in `st.session_state` so Back/Next don't lose data

## The 4 wizard screens

### Screen 1 — Select a stock
- Text input for a ticker symbol (e.g., `LULU`)
- On submit, validate via yfinance and display a confirmation card: company name, sector, current price
- Invalid ticker → friendly inline error, Next button disabled
- Next enabled only once a valid ticker is confirmed

### Screen 2 — Pick competitors (up to 7)
- On entry: Agno peers agent is invoked with the selected ticker; agent returns up to 10 candidate tickers
- All candidates are validated in parallel against yfinance; invalid tickers are silently dropped
- UI: checkbox list showing ticker + company name
- Constraint: user must select 1–7 competitors
- Loading state: "Finding competitors…" spinner during agent call (~5–10s first time, instant on cached re-entry)
- Fallback: if the agent fails, a manual text input lets the user enter tickers directly

### Screen 3 — Finance metrics (comparison table)
- On entry: fetch `.info` via yfinance for the selected stock + all peers, in parallel
- Display: table with stocks as columns, 12 metrics as rows, grouped by the 6 scoring categories
- Values shown as raw data (e.g., "13x fwd P/E", "19.9% op margin", "$58B market cap")
- Missing data shown as "—" (never crashes)
- No scoring on this screen — pure comparison view

### Screen 4 — Ranking & recommendation
- On entry: compute 1–5 category scores for each stock, apply default weights
- **Sliders:** 6 category weight sliders; total must equal 100%. When weights don't sum to 100, show a warning banner but still compute using normalized weights.
- **Live ranking table:** recalculates instantly as sliders move. Shows per-category score + weighted total + rank.
- **AI recommendation:** Agno recommendation agent is called with the top pick + weights + data. Agent writes a 2–3 sentence narrative.
- **Optimization:** recommendation is re-generated only when the top pick changes (not on every slider move) to save tokens.

## Scoring model

### Categories and default weights

| # | Category | Default weight | Primary metric | Direction |
|---|----------|---------------:|----------------|-----------|
| 1 | Valuation | 20% | Forward P/E | Lower is better |
| 2 | Revenue Growth | 20% | YoY revenue growth | Higher is better |
| 3 | Profitability | 20% | Operating margin | Higher is better |
| 4 | Capital Efficiency (ROIC) | 15% | Return on Equity | Higher is better |
| 5 | Financial Health | 15% | Debt/Equity | Lower is better |
| 6 | Dividend Yield | 10% | Dividend yield | Higher is better |

### The 12 displayed metrics

Split across the 6 categories:
1. **Valuation:** Forward P/E, Trailing P/E, PEG ratio, Price/Sales
2. **Revenue Growth:** Revenue growth (YoY), EPS growth
3. **Profitability:** Operating margin, Profit margin
4. **ROIC:** Return on equity (as ROIC proxy)
5. **Financial Health:** Debt/Equity, Beta
6. **Dividend:** Dividend yield

(Each category has one designated primary metric used for scoring; other metrics in the category are shown on Screen 3 for context.)

### Scoring rule (relative ranking)

For each category and its primary metric:
1. Collect the metric value from each selected stock
2. Drop stocks with missing data for this metric (they get neutral score 3 with "no data" display)
3. Determine direction (lower-is-better or higher-is-better)
4. Sort stocks; assign **5** to the best, **1** to the worst
5. Interpolate others linearly across the 1–5 range based on their position

### Final weighted score

```
weighted_score = Σ (category_score × category_weight)
```

Stocks are ranked by `weighted_score` descending. Ties broken alphabetically by ticker.

## File structure

```
stock_analyzer_1/
├── streamlit_app.py              — entry point: `streamlit run streamlit_app.py`
├── app/
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── state.py              — session_state helpers
│   │   ├── nav.py                — progress bar + back/next buttons
│   │   └── screens/
│   │       ├── __init__.py
│   │       ├── step1_select.py
│   │       ├── step2_peers.py
│   │       ├── step3_metrics.py
│   │       └── step4_ranking.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── stock_service.py      — yfinance wrapper + @st.cache_data
│   │   └── scoring_service.py    — pure scoring math (no I/O, no Streamlit)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── peers_agent.py        — Agno agent: ticker → competitor list
│   │   └── recommendation_agent.py — Agno agent: ranking → narrative
│   └── models/
│       ├── __init__.py
│       └── schemas.py            — Pydantic: StockInfo, StockMetrics, CategoryScore, StockRanking
└── tests/
    ├── test_stock_service.py
    ├── test_scoring_service.py
    └── test_agents.py
```

## Data models (Pydantic)

```python
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
    category: str              # "valuation" | "growth" | "profitability" | "roic" | "health" | "dividend"
    score: int                 # 1–5
    raw_value: float | None
    display: str               # human-readable, e.g., "13x fwd P/E"

class StockRanking(BaseModel):
    ticker: str
    category_scores: list[CategoryScore]
    weighted_score: float
    rank: int
```

## Service interfaces

### `app/services/stock_service.py`

```python
@st.cache_data(ttl=600)
def get_stock_info(ticker: str) -> StockInfo | None: ...

@st.cache_data(ttl=600)
def get_stock_metrics(ticker: str) -> StockMetrics | None: ...

def validate_tickers(tickers: list[str]) -> list[str]:
    """Return only the tickers that yfinance recognizes. Runs in parallel."""
```

### `app/services/scoring_service.py`

```python
CATEGORIES = ["valuation", "growth", "profitability", "roic", "health", "dividend"]
DEFAULT_WEIGHTS = {"valuation": 0.20, "growth": 0.20, "profitability": 0.20,
                   "roic": 0.15, "health": 0.15, "dividend": 0.10}

def score_category(
    category: str,
    stocks_metrics: list[StockMetrics],
) -> dict[str, CategoryScore]:
    """Score each stock 1–5 for one category via relative ranking."""

def compute_weighted_scores(
    stocks: list[StockMetrics],
    weights: dict[str, float],
) -> list[StockRanking]:
    """Full pipeline: score all categories → apply weights → sort → assign ranks."""
```

## Agents

### `app/agents/peers_agent.py`
- Agno agent with a system prompt: *"Given the stock {ticker} ({company_name}, {sector}), return up to 10 publicly traded US competitors as JSON: `{\"tickers\": [\"NKE\", \"ADDYY\", ...]}`. Return only real tickers on major exchanges."*
- Output is JSON-parsed; invalid responses → empty list
- Every returned ticker is then validated via `stock_service.validate_tickers()`
- Fallback: on any error, return `[]` — the UI surfaces a manual-entry input

### `app/agents/recommendation_agent.py`
- Agno agent that receives: top-ranked stock's metrics, user's weights, runner-up info
- Returns a 2–3 sentence natural-language recommendation
- No tool calling — plain text generation
- Fallback: on any error, return a deterministic string like "Top pick: {ticker} with weighted score {score:.2f}."

## Error handling

| Failure | Behavior |
|---------|----------|
| Invalid ticker (Screen 1) | Inline error, Next disabled, stay on screen |
| yfinance API down | Banner with Retry button |
| Peers agent fails | Empty peer list + manual text input fallback |
| Recommendation agent fails | Ranking table still shown; narrative replaced with deterministic summary |
| Missing metric for one stock | Cell shows "—"; category score is 3 (neutral) with "no data" indicator |
| All metrics missing for a stock | Stock excluded from ranking with a warning |
| Weights don't sum to 100% | Warning banner; ranking uses normalized weights |

## Testing strategy

- **`tests/test_stock_service.py`** — mock `yfinance.Ticker`; verify field extraction, None handling, cache behavior (~8 tests)
- **`tests/test_scoring_service.py`** — hand-crafted mock stocks; verify scoring direction, tie-breaking, missing-data handling, weight math, full pipeline (~12 tests)
- **`tests/test_agents.py`** — mock Agno responses; verify JSON parsing, ticker validation, fallback paths (~6 tests)
- **No live API or LLM calls in tests** — runs in <2 seconds
- **No Streamlit UI tests** — UI is thin glue; logic is in services

## Success criteria

- [ ] `uv run streamlit run streamlit_app.py` launches the app
- [ ] All 4 wizard screens work end-to-end with a real ticker (e.g., LULU)
- [ ] Peer discovery returns validated tickers via Agno
- [ ] All 12 metrics fetch from yfinance for the selected stocks
- [ ] Sliders recalculate ranking in real-time and sum to 100%
- [ ] Top pick changes trigger a new AI-generated recommendation
- [ ] AI failures gracefully degrade — the app never crashes
- [ ] Back button preserves state on every screen
- [ ] All unit tests pass (`uv run pytest`)
- [ ] `uv run ruff check .` passes with no errors
- [ ] `.env.example` documents required LLM API keys for Agno
- [ ] `CLAUDE.md` is updated with the new run command and project structure

## Dependencies to add

```toml
# pyproject.toml additions
dependencies = [
    "streamlit>=1.40.0",
    "yfinance>=0.2.50",
    # agno, fastapi, pytest, ruff, uvicorn already present
]
```

## Environment variables

```
# .env — add whichever LLM provider Agno is configured to use
OPENAI_API_KEY=sk-...
# or
ANTHROPIC_API_KEY=sk-ant-...
```

## Open questions

None at time of writing. All design decisions are captured in the sections above and were approved during brainstorming on 2026-04-10.
