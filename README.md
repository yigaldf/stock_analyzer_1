# 📈 Stock Analyzer

A 4-step wizard for comparing a stock against its competitors on key financial metrics, with AI-powered peer discovery and weighted ranking recommendations.

Built with **Python**, **Streamlit**, **yfinance**, and **Agno** (OpenAI-backed agents).

---

## Features

- **Step 1 — Select a stock**: Enter any US ticker, see live company info (sector, price, market cap) via yfinance.
- **Step 2 — AI peer discovery**: An Agno agent (GPT-4o) suggests up to 10 direct product-market competitors, validated against yfinance. Manual override lets you add tickers the AI missed.
- **Step 3 — Metrics comparison**: Side-by-side comparison of ~25 metrics grouped into **8 tables** (valuation, growth, profitability, capital efficiency, financial health, cash quality, valuation trend, dividend), a **Forward P/E trend chart** built from each ticker's 5-quarter historical valuation, and a per-ticker **source badge** showing which fetcher backend produced each row (fast httpx path or Playwright fallback). PEG ratio, historical valuation, and same-snapshot pricing are reliable because metrics are read directly from Yahoo's Key Statistics HTML rather than from yfinance's occasionally-`None` fields.
- **Step 4 — Weighted ranking & AI recommendation**: Adjust **8 category weight sliders** to reflect *your* definition of "best" — valuation, growth, profitability, capital efficiency, financial health, **cash quality** (free cash flow yield), **valuation trend** (current forward P/E vs the stock's own 5-quarter historical average), and dividend. Ranking recalculates live. An Agno agent writes a natural-language recommendation for the top pick.
- **Graceful degradation**: If the LLM is unavailable, if Yahoo's anti-bot layer blocks the fast path, or if a metric is missing, the app still works with deterministic fallbacks.

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| UI | Streamlit |
| Data source (Step 1) | yfinance (ticker validation, name/sector/price) |
| Data source (Step 3) | Yahoo Key Statistics HTML, scraped directly |
| HTTP client | httpx (fast-path fetch) |
| HTML parser | selectolax (Lexbor-backed; used for fixture-based and live parsing) |
| Scraper fallback | playwright (headless Chromium, for when Yahoo's anti-bot layer blocks httpx) |
| AI agents | Agno + OpenAI (GPT-4o, GPT-4o-mini) |
| Validation | Pydantic |
| Testing | pytest |
| Lint/format | ruff |
| Package manager | uv |

---

## Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** package manager (`brew install uv` on macOS)
- **OpenAI API key** (for the AI peer discovery and recommendation features)
- **Playwright's Chromium binary** — installed once with `uv run playwright install chromium` (~170 MB, one-time). Only required if Yahoo's anti-bot layer blocks the fast httpx path.

---

## Installation

```bash
# 1. Clone the repo
git clone git@github.com:yigaldf/stock_analyzer_1.git
cd stock_analyzer_1

# 2. Install dependencies
uv sync

# 3. Install Chromium for the scraper's Playwright fallback
#    (only needed on first setup; ~170 MB one-time download)
uv run playwright install chromium

# 4. Configure your API key
cp .env.example .env
# Then edit .env and paste your OpenAI key:
#   OPENAI_API_KEY=sk-...
```

---

## Running the app

```bash
uv run streamlit run streamlit_app.py
```

Streamlit opens a browser tab at [http://localhost:8501](http://localhost:8501).

### Walkthrough

1. **Step 1** — Type a ticker (e.g. `LULU`, `AAPL`, `TSLA`). A confirmation card shows the company name, sector, current price, and market cap.
2. **Step 2** — Wait a few seconds while the AI finds 10 competitors. Check the boxes for the peers you want to compare (1–7). Use the **"➕ Add more tickers manually"** expander to append any the AI missed.
3. **Step 3** — Review the 8 grouped metric tables, the Forward P/E trend chart, and the per-ticker source badge. Missing values show as `—`.
4. **Step 4** — Drag the eight weight sliders. The ranking table recomputes instantly. An AI recommendation paragraph explains why the top pick stands out under your weights.

Use the **← Back** button on any screen to revisit earlier steps; your state is preserved.

---

## How it works

### Architecture — three layers

```
┌──────────────────────────────────────────────────────────────┐
│                    Streamlit UI (app/ui/)                    │
│     Step 1 ─► Step 2 ─► Step 3 ─► Step 4                     │
└───────┬──────────────┬──────────────┬──────────────┬─────────┘
        │              │              │              │
        ▼              ▼              ▼              ▼
   ┌──────────────────────────────────────────────────────┐
   │  Service layer (app/services/)                       │
   │  ─ stock_service.py   (yfinance wrapper, Step 1)     │
   │  ─ yahoo_scraper.py   (Yahoo HTML fetch+parse, Step 3)│
   │  ─ scoring_service.py (pure 8-category scoring math) │
   └──────────────────────────────────────────────────────┘
        │              │              │              │
        ▼              ▼              ▼              ▼
 ┌──────────┐  ┌──────────────────┐  ┌───────────┐  ┌──────────────┐
 │ yfinance │  │ Yahoo Key Stats  │  │peers_agent│  │recommendation│
 │ (Step 1) │  │ HTML (Step 3)    │  │  (Agno,   │  │ agent (Agno, │
 │          │  │ httpx → Playwright│  │  Step 2)  │  │   Step 4)    │
 └──────────┘  └──────────────────┘  └───────────┘  └──────────────┘
```

- **UI layer** — Streamlit screens, thin glue, no business logic
- **Service layer** — pure Python, fully unit-tested, no framework dependencies
- **Agents** — Agno wrappers around OpenAI for peer discovery and narrative generation; all output validated before use
- **Scraper** — `yahoo_scraper.py` runs a tiered fetch: fast `httpx.get()` first, headless Chromium via Playwright only on fallback

### Agent architecture (Agno)

The app uses **[Agno](https://github.com/agno-agi/agno)** — a lightweight Python framework for building LLM agents — for the two places where natural-language reasoning adds real value: **peer discovery** and **recommendation narrative**. Everything else (data fetching, scoring math, ranking) is deterministic Python.

#### Why Agno?

Agno gives us a minimal, typed abstraction over LLM providers:

```python
from agno.agent import Agent
from agno.models.openai import OpenAIChat

agent = Agent(
    model=OpenAIChat(id="gpt-4o"),
    instructions="You are an equity research analyst...",
)
response = agent.run("Stock: LULU — Lululemon Athletica (Consumer Cyclical)...")
text = response.content
```

No framework lock-in, no hidden prompt gymnastics, easy to swap models (GPT-4o, GPT-4o-mini, Claude, etc.). Each agent is a stateless function call: **input → prompt → LLM → text → parsed output**.

#### The two agents

**1. `peers_agent.py` — Competitor discovery** (`suggest_peers(ticker, name, sector)`)

| Piece | Value |
|---|---|
| Model | `gpt-4o` (higher-quality domain knowledge for peer identification) |
| System prompt | Equity-research persona; prefers direct product-market competitors over broad sector matches |
| Input | Ticker + company name + sector |
| Output | Up to 10 candidate tickers as JSON |
| Parser | Two-stage: direct `json.loads`, then regex fallback for LLMs that wrap JSON in prose/markdown |
| Validation | Every returned ticker is then verified against yfinance before being shown to the user |
| Fallback on failure | Empty list → UI offers a manual entry field |

**2. `recommendation_agent.py` — Narrative recommendation** (`generate_recommendation(rankings, weights)`)

| Piece | Value |
|---|---|
| Model | `gpt-4o-mini` (cheaper; this is a text generation task, not a knowledge task) |
| System prompt | "Concise investment analyst"; must reference specific metric values, no financial-advice disclaimers |
| Input | Top-ranked stock's category scores, the user's weight settings, runner-up info |
| Output | A 2–3 sentence recommendation string |
| Fallback on failure | Deterministic summary: *"Top pick: {ticker} with weighted score {score:.2f}."* |
| Optimization | Only re-runs when the **top pick** changes (not on every slider adjustment), to save tokens |

#### Design principles

1. **Agents are leaf nodes, not orchestrators** — they take a plain argument in and return a plain value out. No tool calling, no multi-step reasoning loops. This keeps failures containable.
2. **Lazy imports** — Agno and OpenAI are imported *inside* `_run_agent()`, not at module top level. This lets the unit tests patch `_run_agent` directly without needing any OpenAI key or Agno config to load the module.
3. **Every agent has a deterministic fallback** — if the LLM returns nothing, malformed JSON, or raises any exception, the app falls back to a safe default (empty list, deterministic summary string). The app **never crashes on an AI failure**.
4. **Validated output crosses the boundary** — the peers agent returns a list of strings, but those strings don't reach the UI until they've been verified against yfinance. No hallucinated tickers make it to the comparison table.
5. **Mocked in tests** — `tests/test_peers_agent.py` and `tests/test_recommendation_agent.py` patch `_run_agent` so the 8 agent-related tests run in milliseconds with zero network calls.

#### Agent interaction diagram

```
User input                                User sees
    │                                         ▲
    ▼                                         │
┌───────────────┐                    ┌─────────────────────┐
│ Streamlit UI  │                    │  Streamlit UI       │
│   (Step 2)    │                    │     (Step 4)        │
└───────┬───────┘                    └──────────▲──────────┘
        │ ticker, name, sector                  │ narrative text
        ▼                                       │
┌──────────────────┐                  ┌─────────┴──────────┐
│ suggest_peers()  │                  │ generate_          │
│                  │                  │ recommendation()   │
│  ┌────────────┐  │                  │                    │
│  │ _run_agent │──┼──► OpenAI GPT-4o │  ┌────────────┐    │
│  └────────────┘  │                  │  │ _run_agent │──► OpenAI GPT-4o-mini
│        │         │                  │  └────────────┘    │
│        ▼         │                  │        │           │
│  _extract_       │                  │        ▼           │
│  tickers()       │                  │  raw text (or      │
│        │         │                  │  fallback summary) │
│        ▼         │                  └─────────┬──────────┘
│  validate via    │                            │
│  yfinance        │                            │
└──────────────────┘                            │
        │                                       │
        ▼                                       │
 validated ticker list                  natural-language
                                        recommendation
```

### Scraper architecture — tiered httpx → Playwright fetcher

Step 3's metrics come from scraping **Yahoo Finance's Key Statistics HTML page** directly rather than from yfinance. This is a deliberate choice:

- **PEG ratio reliability** — yfinance's `info` dict frequently returns `None` for `pegRatio` and related fields because the upstream field name changes; the HTML page always renders a value if Yahoo has one.
- **Historical valuation** — Yahoo's Key Statistics page includes a 5-quarter "Valuation Measures" table (Current, and four trailing quarter-ends) that `yfinance` does not expose. This powers Step 3's Forward P/E trend chart and the Valuation Trend scoring category.
- **Same-snapshot pricing** — every metric on the page is consistent with the price and market cap on the same render, so ratios computed downstream don't mix stale and fresh numbers.

The fetcher is **tiered** for speed and resilience:

1. **Fast path — `httpx.get()`** with a realistic browser User-Agent. Typical round-trip: ~200–400 ms per ticker. Succeeds on most tickers most of the time.
2. **Fallback path — headless Chromium via Playwright**. Only triggered when Yahoo returns its anti-bot 404 stub for plain httpx. Typical round-trip: ~3–6 seconds per ticker. Requires the Chromium binary from `uv run playwright install chromium`.

Both backends hand their HTML to the same `selectolax` parser, so parsed output is backend-agnostic. The `source` field on each `StockMetrics` row records which backend ran (`"httpx"`, `"playwright"`, or `"unknown"`).

**Source badges in Step 3**

Each ticker row in Step 3 shows a small badge next to the ticker:

- ⚡ green — served by the fast httpx path
- 🎭 amber — fell back to Playwright (slower, still real data)
- `—` gray — unknown or not recorded

This makes it easy to spot when Yahoo is rate-limiting your IP without having to read logs.

**Maintaining the parser**

The parser's unit tests run against a committed HTML fixture at `tests/fixtures/lulu_key_statistics.html`. If Yahoo ships a layout change that breaks the parser, refresh the fixture from a current LULU page (save the raw HTML, replace the file, re-run `uv run pytest tests/test_yahoo_scraper_parse.py`). The parser tests are fully offline and deterministic once the fixture is in place.

### Scoring model

Each stock is scored **1–5 relative to its peer group** across **8 categories**:

| Category | Weight | Sub-metrics | Direction |
|---|---:|---|---|
| Valuation | 18% | forward_pe, peg_ratio, ev_to_ebitda | Lower better |
| Growth | 18% | revenue_growth_yoy, earnings_growth_yoy | Higher better |
| Profitability | 14% | operating_margin, profit_margin | Higher better |
| Capital Efficiency | 12% | roe, roa | Higher better |
| Financial Health | 12% | debt_to_equity (lower), current_ratio (higher) | Mixed |
| Cash Quality | 12% | FCF yield (levered_free_cash_flow ÷ market_cap) | Higher better |
| Valuation Trend | 8% | current forward_pe ÷ mean historical forward_pe from `valuation_history` (excluding "Current") | Lower better |
| Dividend | 6% | forward_dividend_yield | Higher better |

Composite category scores are the rounded mean of per-sub-metric rankings; derived categories (Cash Quality, Valuation Trend) are scored from a formula, not a single field.

Final ranking = `Σ (category_score × category_weight)`, sorted descending, ties broken alphabetically.

---

## Project structure

```
stock_analyzer_1/
├── streamlit_app.py          # entry point
├── app/
│   ├── models/
│   │   └── schemas.py        # Pydantic models (StockMetrics, ~25 fields)
│   ├── services/
│   │   ├── stock_service.py    # yfinance wrapper (Step 1)
│   │   ├── yahoo_scraper.py    # Yahoo Key Stats HTML fetch + parse (Step 3)
│   │   └── scoring_service.py  # 8-category scoring math
│   ├── agents/
│   │   ├── peers_agent.py    # AI peer discovery
│   │   └── recommendation_agent.py  # AI narrative
│   └── ui/
│       ├── state.py          # session_state helpers
│       ├── nav.py            # wizard navigation
│       └── screens/
│           ├── step1_select.py
│           ├── step2_peers.py
│           ├── step3_metrics.py
│           └── step4_ranking.py
├── tests/                    # 87 unit tests (no live API/LLM calls)
│   └── fixtures/
│       └── lulu_key_statistics.html  # offline fixture for scraper parser tests
├── docs/superpowers/
│   ├── specs/                # design specs
│   └── plans/                # implementation plans
├── pyproject.toml
└── .env.example
```

---

## Development

### Install + run

```bash
uv sync                                # install deps
uv run streamlit run streamlit_app.py  # run the app
```

### Tests

```bash
uv run pytest                # run all tests
uv run pytest -v             # verbose
```

All 87 tests mock yfinance and Agno and parse the committed Yahoo HTML fixture — no live API, LLM, or network calls, runs in under a second.

### Lint & format

```bash
uv run ruff check .    # lint
uv run ruff format .   # format
```

---

## Environment variables

The app reads environment variables from a `.env` file in the project root (loaded via `python-dotenv` on startup).

| Variable | Purpose | Required? |
|---|---|---|
| `OPENAI_API_KEY` | Powers the Agno peer discovery and recommendation agents | Yes (but app degrades gracefully if missing) |

See `.env.example` for the template.

---

## Graceful degradation

The app never crashes on AI or scraper failures:

- **Peer agent fails** → empty list, UI shows a manual entry fallback
- **Recommendation agent fails** → deterministic summary like *"Top pick: ONON with weighted score 4.00"*
- **Missing metric on a stock** → cell shows `—`, category score defaults to neutral 3/5
- **All metrics missing** → stock is excluded from the ranking with a warning
- **Network errors on yfinance** → friendly error banner
- **Yahoo's anti-bot layer blocks httpx** → falls back to headless Chromium via Playwright; source badge shows 🎭 for the affected ticker
- **Playwright binary not installed** → both backends fail, the metrics row shows as missing in Step 3 with the usual "Couldn't fetch metrics for X" warning; app continues

---

## Roadmap / out of scope

**Not included in v1:**

- User accounts, saved comparisons, portfolios
- Historical price charts
- Alerts or watchlists
- Non-US stocks / multi-currency
- Mobile-optimized layout

See [`docs/superpowers/specs/`](docs/superpowers/specs/) for the full design spec and rationale.

---

## License

MIT — see [LICENSE](LICENSE) (or add your preferred license).
