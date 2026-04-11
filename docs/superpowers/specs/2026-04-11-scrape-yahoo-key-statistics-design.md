# Scrape Yahoo Key Statistics — Design

**Date:** 2026-04-11
**Branch:** `web_scraping_metrics`
**Status:** Design approved, pending user review before plan-writing

## Summary

Replace the current `yfinance`-backed fundamentals extraction with a direct HTML scrape of
`https://finance.yahoo.com/quote/{ticker}/key-statistics/`. The expanded data unlocks an 8-category
scoring model in Step 4 (up from 6), including two net-new categories — **Cash Quality** (FCF yield)
and **Valuation Trend** (current vs. 5-quarter historical valuation) — that are only possible because
the scraped page exposes a historical valuation table that `yfinance` does not.

`yfinance` stays in the codebase, restricted to Step 1 work (ticker validation and `StockInfo`) where
it is lighter and faster than scraping.

## Goals

1. Deliver a richer, more reliable metric set for peer comparison in Step 3.
2. Add a historical-valuation signal (Valuation Trend) that `yfinance` structurally cannot provide.
3. Fix the recurring PEG Ratio reliability bug (yfinance returns `None` for many tickers; the HTML
   page has the value).
4. Give every peer a coherent, same-snapshot price context for ratios (one scrape session ≈ one
   moment in time for all peers, vs. yfinance's drifting per-ticker API calls).
5. Keep the existing wizard flow, session state, Agno agents, and scoring pipeline intact.

## Non-goals

- Replacing `yfinance` globally. Step 1 (existence check + name/sector/price) stays on yfinance.
- Persistent or cross-session caching. Streamlit in-memory cache only.
- Rotating user agents, proxies, or anti-detection logic beyond a realistic `User-Agent` header.
- Headless-browser scraping. Plain HTTP + HTML parse only.
- Sector-relative scoring (stays peer-group-relative).
- Internationalization or currency conversion.
- UI changes to Step 1 or Step 2.

## Background

### Current state

`app/services/stock_service.py` calls `yfinance.Ticker(t).info` and extracts 13 fields into a
`StockMetrics` Pydantic model. Step 3 renders a 13-row HTML table. Step 4 uses those metrics in
6 scoring categories, each driven by a single primary metric
(`forward_pe`, `revenue_growth`, `operating_margin`, `roe`, `debt_to_equity`, `dividend_yield`).

### What's wrong with the current state

1. **PEG ratio is often missing** — commit `048ef85` ("Fix empty PEG ratio by reading new yfinance
   field name") shows this is a recurring problem. For LULU today, yfinance returns `null` for both
   `trailingPegRatio` and `pegRatio` even though the Yahoo Key Statistics page shows `0.90`.
2. **Unit bugs** — `debtToEquity` comes as a percentage (`36.245` meaning 36.25%) and must be
   divided by 100 at the call site. This is the kind of quirk that multiplies as metrics grow.
3. **Historical trend is invisible** — `yfinance.info` exposes only the current snapshot. The
   `/key-statistics/` page shows 5 historical quarters of Market Cap, EV, P/E, PEG, P/S, P/B,
   EV/Revenue, EV/EBITDA — a trend signal that's predictive for "is this stock cheap relative to
   its own history?"
4. **Rate-limit fragility** — yfinance's `.info` aggregates multiple internal Yahoo API calls per
   ticker and is increasingly rate-limited. A single HTML fetch per ticker is more forgiving.
5. **Price drift across peers** — yfinance samples peer A at one moment and peer B at another,
   so ratios using `currentPrice` are not internally coherent. A single scrape session for all
   peers sees one price snapshot.

### Empirical validation

During brainstorming we fetched LULU from both sources on 2026-04-11 and built a side-by-side
comparison:

| Category of field | Match? |
|---|---|
| Non-price fundamentals (margins, returns, revenue, cash flow, debt, beta, share stats) | **100% exact match** to the last decimal |
| Price-dependent ratios (P/E, P/S, P/B, EV multiples) | Drift by 0-20% due to yfinance and Yahoo sampling price at different moments |
| PEG Ratio | yfinance `None`, page `0.90` — yfinance decisively wrong |
| Historical valuation (5 quarters) | Not exposed by yfinance |

This proved two things: scraped values are trustworthy (they're what Yahoo officially displays),
and yfinance's current-snapshot ratios have drift that peer comparisons are sensitive to.

## Architecture

### Three-layer structure (unchanged)

```
Streamlit UI (app/ui/)
    ↓
Services (app/services/)    ← scoring_service and the new yahoo_scraper live here
    ↓
External data sources: yfinance (Step 1) + Yahoo HTML scrape (Step 3)
```

### Module inventory

| Module | Role | Change |
|---|---|---|
| `app/services/yahoo_scraper.py` | **NEW** — fetches & parses `/key-statistics/` HTML | Created |
| `app/services/stock_service.py` | `get_stock_metrics` now delegates to scraper | Modified (small) |
| `app/services/scoring_service.py` | 8 categories, composite scoring, derived metrics | Rewritten |
| `app/models/schemas.py` | `StockMetrics` expanded, new `QuarterlyValuation` type | Modified |
| `app/ui/screens/step3_metrics.py` | Grouped tables by section + Forward P/E trend chart | Modified |
| `app/ui/screens/step4_ranking.py` | 8 weight sliders, new category labels | Modified |
| `app/agents/recommendation_agent.py` | Prompt regenerated with new category names | Modified (prompt only) |
| `tests/fixtures/lulu_key_statistics.html` | **NEW** — committed HTML fixture | Created |
| `tests/test_yahoo_scraper_*.py` | **NEW** — converter, parse, fetch tests | Created |
| `tests/test_scoring_*.py` | **NEW / updated** — composite, derived, integration | Created / updated |
| `tests/test_schemas.py` | Updated for new fields | Modified |

### Data flow

```
Step 1 (ticker picker)
  → stock_service.validate_tickers()     [yfinance]
  → stock_service.get_stock_info()       [yfinance]

Step 2 (peer discovery)
  → peers_agent.run() + sector filter    [Agno + yfinance]

Step 3 (metric table + trend chart)
  → stock_service.get_stock_metrics()
  → yahoo_scraper.fetch()                [httpx + selectolax, @st.cache_data(ttl=10800)]

Step 4 (ranking)
  → scoring_service.compute_weighted_scores()   [pure Python]
  → recommendation_agent.generate_recommendation()   [Agno + LLM]
```

## Data model

```python
# app/models/schemas.py

class QuarterlyValuation(BaseModel):
    """One column from Yahoo's Valuation Measures table."""
    period: str                   # "Current" | "12/31/2025" | "9/30/2025" | ...
    market_cap: float | None
    enterprise_value: float | None
    trailing_pe: float | None
    forward_pe: float | None
    peg_ratio: float | None
    price_to_sales: float | None
    price_to_book: float | None
    ev_to_revenue: float | None
    ev_to_ebitda: float | None


class StockMetrics(BaseModel):
    ticker: str

    # Valuation (current snapshot — mirrors the "Current" column in valuation_history)
    forward_pe: float | None
    trailing_pe: float | None
    peg_ratio: float | None
    price_to_sales: float | None
    price_to_book: float | None
    ev_to_revenue: float | None
    ev_to_ebitda: float | None
    market_cap: float | None
    enterprise_value: float | None

    # Profitability
    profit_margin: float | None           # as decimal: 0.1422
    operating_margin: float | None

    # Capital efficiency
    roe: float | None
    roa: float | None

    # Growth
    revenue_growth_yoy: float | None      # Qtrly Revenue Growth (yoy)
    earnings_growth_yoy: float | None     # Qtrly Earnings Growth (yoy)

    # Financial health
    debt_to_equity: float | None          # ratio, not percent: 0.3625
    current_ratio: float | None
    total_cash: float | None              # raw dollars
    total_debt: float | None

    # Cash quality
    operating_cash_flow: float | None
    levered_free_cash_flow: float | None

    # Risk / display
    beta: float | None

    # Dividend
    forward_dividend_yield: float | None  # decimal; None when "--"
    payout_ratio: float | None

    # Historical trend (5 quarters + "Current" = typically 6 entries)
    valuation_history: list[QuarterlyValuation] = []
```

### Unit & format rules

- Percentages stored as decimals (`0.1422`, never `14.22`).
- Monetary values stored as raw floats in dollars (`1_810_000_000.0`, never `"1.81B"`).
- `"--"` on the Yahoo page → `None` in the model.
- `None` is a first-class signal throughout the pipeline; UI renders it as `"—"`, scoring treats
  it as neutral (score = 3).

### Fields deliberately dropped

Trailing dividend fields, all date fields (ex-dividend, split date, fiscal year), revenue per
share, book value per share, average volume, shares outstanding / float, % held insiders, all
short-interest variants, moving averages, 52-week range, S&P comparison. These were classified as
Tier 3 ("low predictive value / metadata") during brainstorming and will not be parsed or stored.

## The scraper module

### Public surface

```python
# app/services/yahoo_scraper.py

def fetch(ticker: str) -> StockMetrics | None:
    """Fetch and parse Yahoo Key Statistics for one ticker.

    Returns None on any hard failure (network, non-200, unparseable document).
    Returns a partial StockMetrics with None-filled fields if some sections
    are missing or unparseable.
    """
```

Exactly one public symbol. Everything else private.

### Internals

```
_URL_TEMPLATE  = "https://finance.yahoo.com/quote/{ticker}/key-statistics/?guccounter=1"
_HEADERS       = {"User-Agent": "...", "Accept-Language": "en-US,en;q=0.9"}
_TIMEOUT       = 10  # seconds
_client        = httpx.Client(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True)

def _fetch_html(ticker) -> str | None
def _parse_document(html, ticker) -> StockMetrics | None
def _parse_valuation_table(doc) -> tuple[dict, list[QuarterlyValuation]]
def _parse_stat_table(doc, heading_text, label_map) -> dict[str, float | None]

def _to_float(s: str | None) -> float | None      # "12.37" -> 12.37
def _to_percent(s: str | None) -> float | None    # "14.22%" -> 0.1422, "-21.60%" -> -0.216
def _to_magnitude(s: str | None) -> float | None  # "1.81B" -> 1_810_000_000.0
```

### Parser strategy

For each flat (single-column) section, a constant dict maps Yahoo's exact label string to a
`(schema_field, converter)` tuple:

```python
_PROFITABILITY_MAP = {
    "Profit Margin":          ("profit_margin", _to_percent),
    "Operating Margin (ttm)": ("operating_margin", _to_percent),
}

_MANAGEMENT_MAP = {
    "Return on Assets (ttm)": ("roa", _to_percent),
    "Return on Equity (ttm)": ("roe", _to_percent),
}

_INCOME_MAP = {
    "Quarterly Revenue Growth (yoy)":  ("revenue_growth_yoy", _to_percent),
    "Quarterly Earnings Growth (yoy)": ("earnings_growth_yoy", _to_percent),
}

_BALANCE_SHEET_MAP = {
    "Total Cash (mrq)":        ("total_cash",     _to_magnitude),
    "Total Debt (mrq)":        ("total_debt",     _to_magnitude),
    "Total Debt/Equity (mrq)": ("debt_to_equity", _to_percent),
    "Current Ratio (mrq)":     ("current_ratio",  _to_float),
}

_CASHFLOW_MAP = {
    "Operating Cash Flow (ttm)":    ("operating_cash_flow",    _to_magnitude),
    "Levered Free Cash Flow (ttm)": ("levered_free_cash_flow", _to_magnitude),
}

_PRICE_HISTORY_MAP = {
    "Beta (5Y Monthly)": ("beta", _to_float),
}

_DIVIDEND_MAP = {
    "Forward Annual Dividend Yield 4": ("forward_dividend_yield", _to_percent),
    "Payout Ratio 4":                  ("payout_ratio",           _to_percent),
}
```

`_parse_stat_table` walks the rows of one `<table>`, matches the first cell exactly against the
label map, and sets fields accordingly. Unknown rows are silently skipped.

### Valuation table (special case)

The Valuation Measures table is a 7-column grid (label + "Current" + 5 quarter columns).

1. Read the header row → build `period_labels: list[str]`.
2. For each data row, match the label in a `_VALUATION_MAP` (same `field, converter` pattern).
3. For each non-header cell, populate the corresponding `QuarterlyValuation` in a list indexed
   by period.
4. Return both `(current_snapshot_dict, valuation_history)`.
5. The current snapshot becomes the top-level `StockMetrics` fields (forward_pe, peg_ratio, etc.)
   so that `valuation_history[0]` and the top-level fields agree.

### Converter edge cases

| Converter | Input | Output |
|---|---|---|
| `_to_float` | `"12.37"` | `12.37` |
| `_to_float` | `"1,234.56"` | `1234.56` |
| `_to_float` | `"--"`, `""`, `None` | `None` |
| `_to_percent` | `"14.22%"` | `0.1422` |
| `_to_percent` | `"-21.60%"` | `-0.216` |
| `_to_percent` | `"--"`, `""` | `None` |
| `_to_magnitude` | `"1.81B"` | `1_810_000_000.0` |
| `_to_magnitude` | `"824.08M"` | `824_080_000.0` |
| `_to_magnitude` | `"350K"` | `350_000.0` |
| `_to_magnitude` | `"123"` | `123.0` |
| `_to_magnitude` | `"--"` | `None` |

### Error handling

| Failure mode | Behavior |
|---|---|
| httpx network error or timeout | log warning, return `None` |
| HTTP status ≠ 200 | log warning, return `None` |
| `selectolax` parse error on document root | log warning, return `None` |
| Expected section (heading) not found | log warning, affected fields `None`, continue other sections |
| Row label unknown to any map | silently skipped |
| Cell value unparseable | field `None` |
| Valuation table header has unexpected shape | top-level valuation fields populated best-effort, `valuation_history = []` |

**Invariant:** hard failures return `None` from `fetch()`; soft failures return a partial
`StockMetrics`. Upstream code already handles both cases (Step 3's "Couldn't fetch metrics for: X"
warning and the scoring service's neutral-3 fallback for missing fields).

### Caching

```python
@st.cache_data(ttl=10800)  # 3 hours
def fetch(ticker: str) -> StockMetrics | None:
    ...
```

Rationale: Yahoo's page updates intraday for price-dependent fields and once per quarter for the
rest. 3 hours is the user's preferred balance between freshness and avoiding re-scrapes across a
single analysis session.

### Concurrency

Step 3 already calls `get_stock_metrics` sequentially in a for-loop. Keep it sequential — with the
3-hour cache and typical peer groups of 4-8, cold-start latency is ~4-12 seconds one time per
ticker per session. If this becomes a problem, a `ThreadPoolExecutor(max_workers=4)` wrapper is a
trivial drop-in.

### HTTP client lifetime

One module-level `httpx.Client()` reused across calls. Streamlit runs in a single process; no
explicit close — the client dies with the process.

### New runtime dependencies

```toml
"httpx>=0.27.0",
"selectolax>=0.3.21",
```

### New test dependency

```toml
"pytest-httpx>=0.30.0",  # or respx — whichever proves cleaner
```

## Scoring service

### Categories

| # | ID | Label | Metrics | Direction |
|---|---|---|---|---|
| 1 | `valuation` | Valuation | `forward_pe`, `peg_ratio`, `ev_to_ebitda` | lower better |
| 2 | `growth` | Growth | `revenue_growth_yoy`, `earnings_growth_yoy` | higher better |
| 3 | `profitability` | Profitability | `operating_margin`, `profit_margin` | higher better |
| 4 | `capital_efficiency` | Capital Efficiency | `roe`, `roa` | higher better |
| 5 | `health` | Financial Health | `debt_to_equity` (lower), `current_ratio` (higher) | mixed |
| 6 | `cash_quality` | Cash Quality | derived: `levered_free_cash_flow / market_cap` | higher better |
| 7 | `valuation_trend` | Valuation Trend | derived: current `forward_pe` ÷ mean of historical `forward_pe` from `valuation_history` | lower better |
| 8 | `dividend` | Dividend | `forward_dividend_yield` | higher better |

### Default weights

```python
DEFAULT_WEIGHTS = {
    "valuation":          0.18,
    "growth":             0.18,
    "profitability":      0.14,
    "capital_efficiency": 0.12,
    "health":             0.12,
    "cash_quality":       0.12,
    "valuation_trend":    0.08,
    "dividend":           0.06,
}
```

Sum = 1.00. Normalized at runtime even if the user adjusts sliders (existing behavior).

### Composite scoring mechanic

For a composite category, each sub-metric is scored 1-5 independently using the existing
peer-group relative ranking logic, then the sub-scores are averaged and rounded:

```
composite_score = round(mean(sub_score_1, sub_score_2, ...))
```

Missing-data handling: if a peer is missing one sub-metric but not others, it receives neutral 3
for that sub-metric only and contributes its available sub-scores to the mean. If all peers are
missing a sub-metric, every peer gets 3 for that sub-metric (existing behavior).

### Mixed-direction composites (Financial Health)

The existing `score_category` handles one direction per call. Refactor it into
`score_category_single(stocks, field, direction)` and have the composite scorer iterate per
sub-metric with its own direction:

```python
def _score_composite(
    stocks: list[StockMetrics],
    sub_metrics: list[tuple[str, str]],   # [(field, direction), ...]
) -> dict[str, int]:
    per_submetric = [
        score_category_single(stocks, field, direction)
        for field, direction in sub_metrics
    ]
    return {
        s.ticker: round(mean(d[s.ticker].score for d in per_submetric))
        for s in stocks
    }
```

### Derived metrics

**Cash Quality** computes `fcf_yield = levered_free_cash_flow / market_cap` per stock into a
temporary list, then ranks that list using `score_category_single(..., "higher")`. If either
input is `None` or `market_cap == 0`, `fcf_yield` is `None` and the peer receives neutral 3 for
this category.

**Valuation Trend** computes `trend_ratio = current_forward_pe / historical_mean` where
`historical_mean` is the arithmetic mean of `forward_pe` across all entries in
`valuation_history` whose `period != "Current"` and whose `forward_pe is not None`. The "Current"
entry is deliberately excluded so the ratio compares "now" against "own recent history". Then
ranks with `"lower"` direction (ratio < 1.0 = cheaper than own history = better). Edge cases:

- Fewer than 1 non-Current historical entry with a non-None `forward_pe` → `trend_ratio = None`
  → neutral 3.
- `historical_mean == 0` → `None` → neutral 3.
- `current_forward_pe is None` → `None` → neutral 3.
- Any peer missing `valuation_history` entirely → neutral 3.

### Category-to-scorer dispatch

```python
CATEGORIES = [
    "valuation", "growth", "profitability", "capital_efficiency",
    "health", "cash_quality", "valuation_trend", "dividend",
]

_CATEGORY_SUBMETRICS = {
    "valuation":          [("forward_pe", "lower"), ("peg_ratio", "lower"), ("ev_to_ebitda", "lower")],
    "growth":             [("revenue_growth_yoy", "higher"), ("earnings_growth_yoy", "higher")],
    "profitability":      [("operating_margin", "higher"), ("profit_margin", "higher")],
    "capital_efficiency": [("roe", "higher"), ("roa", "higher")],
    "health":             [("debt_to_equity", "lower"), ("current_ratio", "higher")],
    "dividend":           [("forward_dividend_yield", "higher")],
}
# cash_quality + valuation_trend handled by dedicated functions

def score_category(category, stocks) -> dict[str, CategoryScore]:
    if category == "cash_quality":      return _score_cash_quality(stocks)
    if category == "valuation_trend":   return _score_valuation_trend(stocks)
    return _score_composite(stocks, _CATEGORY_SUBMETRICS[category])
```

`compute_weighted_scores` keeps its current signature and sort/rank logic — only the category
list and per-category computation change. `StockRanking` schema is unchanged, so the
recommendation agent and Step 4's rendering layer see the same shape.

### Display strings

`CategoryScore.display` for composite categories shows the averaged raw value annotations, e.g.:

```
growth:          "4/5  (Rev +22.6%, EPS -22.9%)"
cash_quality:    "5/5  (FCF yield 2.4%)"
valuation_trend: "2/5  (Fwd P/E now 0.79× avg)"
```

This is a UI nicety; if it adds complexity we'll fall back to `"4/5"` alone.

## UI changes

### Step 3 — `app/ui/screens/step3_metrics.py`

The single 13-row table becomes **grouped tables by section**, reusing the existing
`metrics-table` CSS class. The `_METRIC_ROWS` constant becomes `_METRIC_GROUPS`:

```python
_METRIC_GROUPS = [
    ("Valuation", [
        ("Forward P/E",    "forward_pe",     lambda v: f"{v:.1f}x"),
        ("Trailing P/E",   "trailing_pe",    lambda v: f"{v:.1f}x"),
        ("PEG (5Y)",       "peg_ratio",      lambda v: f"{v:.2f}"),
        ("Price/Sales",    "price_to_sales", lambda v: f"{v:.1f}"),
        ("Price/Book",     "price_to_book",  lambda v: f"{v:.1f}"),
        ("EV/EBITDA",      "ev_to_ebitda",   lambda v: f"{v:.1f}"),
        ("EV/Revenue",     "ev_to_revenue",  lambda v: f"{v:.1f}"),
    ]),
    ("Profitability", [
        ("Operating Margin", "operating_margin", lambda v: f"{v*100:.1f}%"),
        ("Profit Margin",    "profit_margin",    lambda v: f"{v*100:.1f}%"),
    ]),
    ("Capital Efficiency", [
        ("ROE", "roe", lambda v: f"{v*100:.1f}%"),
        ("ROA", "roa", lambda v: f"{v*100:.1f}%"),
    ]),
    ("Growth", [
        ("Revenue Growth (yoy)",  "revenue_growth_yoy",  lambda v: f"{v*100:.1f}%"),
        ("Earnings Growth (yoy)", "earnings_growth_yoy", lambda v: f"{v*100:.1f}%"),
    ]),
    ("Financial Health", [
        ("Debt/Equity",  "debt_to_equity", lambda v: f"{v*100:.1f}%"),
        ("Current Ratio","current_ratio",  lambda v: f"{v:.2f}"),
        ("Total Cash",   "total_cash",     lambda v: f"${v/1e9:.2f}B"),
        ("Total Debt",   "total_debt",     lambda v: f"${v/1e9:.2f}B"),
    ]),
    ("Cash Flow", [
        ("Operating Cash Flow",     "operating_cash_flow",    lambda v: f"${v/1e9:.2f}B"),
        ("Levered Free Cash Flow",  "levered_free_cash_flow", lambda v: f"${v/1e9:.2f}B"),
    ]),
    ("Market Context", [
        ("Beta (5Y)",       "beta",             lambda v: f"{v:.2f}"),
        ("Market Cap",      "market_cap",       lambda v: f"${v/1e9:.2f}B"),
        ("Enterprise Value","enterprise_value", lambda v: f"${v/1e9:.2f}B"),
    ]),
    ("Dividend", [
        ("Forward Dividend Yield", "forward_dividend_yield", lambda v: f"{v*100:.2f}%"),
        ("Payout Ratio",           "payout_ratio",           lambda v: f"{v*100:.1f}%"),
    ]),
]
```

The render loop emits one `st.markdown(f"#### {group_name}")` subheader plus one HTML table per
group.

### Forward P/E trend chart

Under the Valuation group, render a `st.line_chart` from `valuation_history`:

```python
trend_df = pd.DataFrame(
    {m.ticker: [q.forward_pe for q in m.valuation_history] for m in metrics_list},
    index=[q.period for q in metrics_list[0].valuation_history],
)
st.markdown("##### Forward P/E trend (5 quarters)")
st.line_chart(trend_df)
```

Silently skipped if `valuation_history` is empty or peer period lists disagree.

### Step 4 — `app/ui/screens/step4_ranking.py`

6 sliders → 8 sliders in the existing 3-column grid. New labels:

```python
_CATEGORY_LABELS = {
    "valuation":          "Valuation",
    "growth":             "Growth",
    "profitability":      "Profitability",
    "capital_efficiency": "Capital Efficiency",
    "health":             "Financial Health",
    "cash_quality":       "Cash Quality",
    "valuation_trend":    "Valuation Trend",
    "dividend":           "Dividend",
}
```

Slider defaults from `DEFAULT_WEIGHTS`. All normalization, warning, and rendering logic is
otherwise unchanged. The ranking table grows from 6 to 8 category columns.

### Recommendation agent

`recommendation_agent.py` receives `StockRanking` objects whose shape is unchanged; only the
`category` string values in `category_scores` differ. The agent's prompt must be updated to
mention the new category names (Capital Efficiency, Cash Quality, Valuation Trend) and briefly
explain what each represents so the LLM can reason about them. Prompt-only change; no
architectural impact.

## Testing

### Test inventory

**New unit tests**

| File | What it covers |
|---|---|
| `tests/test_yahoo_scraper_converters.py` | `_to_float`, `_to_percent`, `_to_magnitude` — happy path, `"--"`, empty, `None`, negative percents, leading sign, `1,234.56` grouping, `B`/`M`/`K` suffixes |
| `tests/test_yahoo_scraper_parse.py` | Full parse against `tests/fixtures/lulu_key_statistics.html` — asserts every field matches the known-correct LULU values captured 2026-04-11 |
| `tests/test_yahoo_scraper_fetch.py` | `fetch()` end-to-end with `pytest-httpx` mocks: 200 OK + fixture → full metrics; 503 → `None`; timeout → `None`; HTML with one section removed → partial metrics |
| `tests/test_scoring_composite.py` | Composite scoring math: 3-peer scenarios per composite category with handcrafted values |
| `tests/test_scoring_derived.py` | Cash Quality (FCF yield derivation + ranking) and Valuation Trend (trend ratio from `valuation_history`) |
| `tests/test_scoring_full.py` | `compute_weighted_scores` integration: 4 peers × 8 categories × default weights |

**Updated tests**

| File | Change |
|---|---|
| `tests/test_schemas.py` | New `StockMetrics` field set; `QuarterlyValuation` roundtrip test |
| Existing scoring tests | Ported to new category IDs and `score_category_single` |

### Fixture policy

- `tests/fixtures/lulu_key_statistics.html` — one real HTML page captured from the live Yahoo site
  on 2026-04-11, committed to git.
- Expected values live in a Python constant inside the parse test, hand-verified from the
  side-by-side comparison done during brainstorming.
- Refresh is manual: when Yahoo changes the HTML structure and parse tests fail, the developer
  regenerates the fixture and updates expected values in the same commit.
- This is the standard approach for HTML parsers and gives deterministic, offline-capable tests.

### Manual smoke test

1. `uv run streamlit run streamlit_app.py`
2. Step 1: pick `LULU`.
3. Step 2: accept peer suggestions (NKE, ADDYY, ONON, etc.).
4. Step 3: verify all 8 metric groups render with non-`—` values for LULU; verify the Forward P/E
   trend chart shows 5 quarters of lines per peer.
5. Step 4: verify 8 sliders; move Cash Quality to 100% and confirm ranking reorders to favor the
   peer with highest FCF yield; verify the AI recommendation mentions the new category names.

## Implementation order

1. Add `httpx`, `selectolax`, `pytest-httpx` to `pyproject.toml`; `uv sync`.
2. Update `StockMetrics` and add `QuarterlyValuation` in `app/models/schemas.py`; schema tests
   pass.
3. Implement converters (`_to_float`, `_to_percent`, `_to_magnitude`) in `yahoo_scraper.py`;
   converter tests pass.
4. Capture live LULU HTML → `tests/fixtures/lulu_key_statistics.html`; implement `_parse_*`
   functions; parse tests pass against fixture.
5. Implement `fetch()` with httpx client + `@st.cache_data(ttl=10800)`; fetch tests pass.
6. Replace `stock_service.get_stock_metrics()` body with `yahoo_scraper.fetch(ticker)`; existing
   integration tests pass.
7. Refactor `scoring_service.py` → `score_category_single`, composite scorer, derived scorers;
   all scoring tests pass.
8. Update `step3_metrics.py` → grouped tables + Forward P/E trend chart; manual smoke.
9. Update `step4_ranking.py` → 8 sliders + new labels; manual smoke.
10. Update `recommendation_agent.py` prompt to describe the new category names; manual smoke.
11. End-to-end smoke test with a real ticker.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Yahoo changes the HTML structure | Label-exact match fails loudly in parse tests; fix fixture + parser together |
| Yahoo blocks scraping from user's IP | Caller sees `None` metrics, Step 3 shows existing "Couldn't fetch" warning, app continues |
| PEG or other field shows `"--"` on Yahoo | Converter returns `None`; scoring assigns neutral 3 (existing behavior) |
| `valuation_history` < 2 quarters available | Valuation Trend returns neutral 3 for all peers; trend chart skipped |
| `selectolax` wheel unavailable on user's platform | Extremely unlikely; fallback to `beautifulsoup4` + `lxml` if it ever happens |
| Peers have different `period` labels in history (fiscal-year mismatch) | Trend chart skipped silently; Valuation Trend scoring still works per-peer |

## Out of scope

- Disk/cross-session caching
- Alternative data sources (AlphaVantage, Finnhub, direct company filings)
- Historical analysis beyond 5 quarters
- Sector-relative scoring
- Z-scores, outlier trimming, or other statistical refinements to the 1-5 ranking
- Internationalization or currency conversion
- Step 1 and Step 2 UI changes
