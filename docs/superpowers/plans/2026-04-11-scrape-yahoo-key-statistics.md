# Scrape Yahoo Key Statistics — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `yfinance`-backed Step 3 metrics fetch with a direct HTML scrape of Yahoo's `/key-statistics/` page, expand `StockMetrics` to ~22 fields plus 5-quarter valuation history, and grow scoring from 6 to 8 categories (adding Cash Quality and Valuation Trend).

**Architecture:** A new `app/services/yahoo_scraper.py` module owns one public `fetch(ticker) -> StockMetrics | None` function. Internally it issues a single `httpx` GET to `finance.yahoo.com/quote/{ticker}/key-statistics/`, parses the HTML with `selectolax`, and walks each statistics table using exact-label dispatch dicts. `stock_service.get_stock_metrics` becomes a thin wrapper around `yahoo_scraper.fetch`. `scoring_service` is refactored so that each category is scored as either a composite of single-metric sub-scores or a derived metric (Cash Quality from FCF yield, Valuation Trend from current-vs-historical Forward P/E ratio).

**Tech Stack:** Python 3.12, `httpx` (HTTP client), `selectolax` (HTML parser), `pytest-httpx` (HTTP mocking), Pydantic (schemas), Streamlit (UI), `pandas` (Forward P/E trend chart).

**Reference design:** [docs/superpowers/specs/2026-04-11-scrape-yahoo-key-statistics-design.md](../specs/2026-04-11-scrape-yahoo-key-statistics-design.md)

---

## Task 1: Add runtime and test dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `httpx`, `selectolax`, and `pytest-httpx` to `pyproject.toml`**

In `pyproject.toml`, replace the `dependencies` array with:

```toml
dependencies = [
    "agno>=2.5.14",
    "fastapi>=0.135.3",
    "pytest>=9.0.3",
    "ruff>=0.15.9",
    "uvicorn>=0.44.0",
    "streamlit>=1.40.0",
    "yfinance>=0.2.50",
    "pydantic>=2.0.0",
    "openai>=2.31.0",
    "httpx>=0.27.0",
    "selectolax>=0.3.21",
    "pytest-httpx>=0.30.0",
]
```

`yfinance` stays in the list — Step 1 (`validate_tickers`, `get_stock_info`) continues to use it.

- [ ] **Step 2: Sync the lockfile**

Run: `uv sync`
Expected: New packages installed; `uv.lock` updated; no errors.

- [ ] **Step 3: Verify imports work**

Run: `uv run python -c "import httpx, selectolax, pytest_httpx; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add httpx, selectolax, pytest-httpx for Yahoo scraping"
```

---

## Task 2: Expand `StockMetrics` schema and add `QuarterlyValuation`

**Files:**
- Modify: `app/models/schemas.py`
- Modify: `tests/test_schemas.py`

- [ ] **Step 1: Read the existing `tests/test_schemas.py` to learn the existing patterns**

Run: `cat tests/test_schemas.py` (use Read tool, not bash)
Goal: Understand which Pydantic patterns the existing tests use, so new tests match.

- [ ] **Step 2: Write a failing test for `QuarterlyValuation`**

Append to `tests/test_schemas.py`:

```python
from app.models.schemas import QuarterlyValuation


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
```

- [ ] **Step 3: Run the new tests, verify they fail**

Run: `uv run pytest tests/test_schemas.py::test_quarterly_valuation_roundtrip tests/test_schemas.py::test_quarterly_valuation_allows_none_for_all_numerics -v`
Expected: FAIL — `ImportError: cannot import name 'QuarterlyValuation'`

- [ ] **Step 4: Add `QuarterlyValuation` to `app/models/schemas.py`**

Edit `app/models/schemas.py`. Insert after `StockInfo` and before `StockMetrics`:

```python
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
```

- [ ] **Step 5: Run the QuarterlyValuation tests, verify they pass**

Run: `uv run pytest tests/test_schemas.py::test_quarterly_valuation_roundtrip tests/test_schemas.py::test_quarterly_valuation_allows_none_for_all_numerics -v`
Expected: PASS

- [ ] **Step 6: Write a failing test for the expanded `StockMetrics`**

Append to `tests/test_schemas.py`:

```python
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
```

Note: the existing `StockMetrics` has all numeric fields as required. The new schema makes them all optional with `None` defaults so a partial scrape returns a valid model. The test above uses positional/keyword pairs that exercise this.

- [ ] **Step 7: Run the new StockMetrics tests, verify they fail**

Run: `uv run pytest tests/test_schemas.py::test_stock_metrics_has_new_fields tests/test_schemas.py::test_stock_metrics_with_valuation_history -v`
Expected: FAIL — `roa`, `current_ratio`, `valuation_history` etc. are not on the model.

- [ ] **Step 8: Replace the `StockMetrics` class in `app/models/schemas.py`**

Edit `app/models/schemas.py`. Replace the entire `StockMetrics` class with:

```python
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
```

- [ ] **Step 9: Run the new StockMetrics tests, verify they pass**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: PASS for all schema tests.

- [ ] **Step 10: Run the full test suite to see what else broke**

Run: `uv run pytest -x`
Expected: FAILS in `tests/test_scoring_service.py` and `tests/test_stock_service.py` because the old fields (`revenue_growth`, `eps_growth`, `dividend_yield`) were removed. That's expected — those modules will be updated in later tasks.

- [ ] **Step 11: Commit**

```bash
git add app/models/schemas.py tests/test_schemas.py
git commit -m "schema: expand StockMetrics and add QuarterlyValuation for scraped data"
```

---

## Task 3: Scaffold the scraper module with converter functions

**Files:**
- Create: `app/services/yahoo_scraper.py`
- Create: `tests/test_yahoo_scraper_converters.py`

- [ ] **Step 1: Write failing tests for `_to_float`**

Create `tests/test_yahoo_scraper_converters.py`:

```python
from app.services.yahoo_scraper import _to_float, _to_magnitude, _to_percent


def test_to_float_simple():
    assert _to_float("12.37") == 12.37


def test_to_float_with_thousands_separator():
    assert _to_float("1,234.56") == 1234.56


def test_to_float_negative():
    assert _to_float("-7.5") == -7.5


def test_to_float_dash_returns_none():
    assert _to_float("--") is None


def test_to_float_empty_returns_none():
    assert _to_float("") is None


def test_to_float_none_returns_none():
    assert _to_float(None) is None


def test_to_float_whitespace_returns_none():
    assert _to_float("   ") is None
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_yahoo_scraper_converters.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.yahoo_scraper'`

- [ ] **Step 3: Create `app/services/yahoo_scraper.py` with `_to_float`**

Create `app/services/yahoo_scraper.py`:

```python
"""Yahoo Finance Key Statistics scraper.

Public surface: `fetch(ticker)` returns a `StockMetrics` (possibly partial)
or `None` on hard failure.
"""
from __future__ import annotations


def _to_float(s: str | None) -> float | None:
    """Parse a plain decimal string. Handles thousands separators and `--`."""
    if s is None:
        return None
    cleaned = s.strip().replace(",", "")
    if not cleaned or cleaned == "--":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None
```

- [ ] **Step 4: Run `_to_float` tests, verify they pass**

Run: `uv run pytest tests/test_yahoo_scraper_converters.py -v -k to_float`
Expected: PASS

- [ ] **Step 5: Write failing tests for `_to_percent`**

Append to `tests/test_yahoo_scraper_converters.py`:

```python
def test_to_percent_positive():
    assert _to_percent("14.22%") == 0.1422


def test_to_percent_negative():
    assert _to_percent("-21.60%") == -0.216


def test_to_percent_with_thousands():
    assert _to_percent("1,234.50%") == 12.345


def test_to_percent_dash_returns_none():
    assert _to_percent("--") is None


def test_to_percent_empty_returns_none():
    assert _to_percent("") is None


def test_to_percent_none_returns_none():
    assert _to_percent(None) is None


def test_to_percent_no_percent_sign_still_parses():
    # Yahoo occasionally renders raw numbers in a column we expected as %.
    # Treat the bare number as already-percent-form: "14.22" -> 0.1422.
    assert _to_percent("14.22") == 0.1422
```

- [ ] **Step 6: Run new tests, verify they fail**

Run: `uv run pytest tests/test_yahoo_scraper_converters.py -v -k to_percent`
Expected: FAIL — `_to_percent` not defined.

- [ ] **Step 7: Add `_to_percent` to `app/services/yahoo_scraper.py`**

Append to `app/services/yahoo_scraper.py`:

```python
def _to_percent(s: str | None) -> float | None:
    """Parse `14.22%` or `-21.60%` -> 0.1422 / -0.216. `--` -> None."""
    if s is None:
        return None
    cleaned = s.strip().replace(",", "").rstrip("%")
    if not cleaned or cleaned == "--":
        return None
    try:
        return float(cleaned) / 100.0
    except ValueError:
        return None
```

- [ ] **Step 8: Run `_to_percent` tests, verify they pass**

Run: `uv run pytest tests/test_yahoo_scraper_converters.py -v -k to_percent`
Expected: PASS

- [ ] **Step 9: Write failing tests for `_to_magnitude`**

Append to `tests/test_yahoo_scraper_converters.py`:

```python
def test_to_magnitude_billions():
    assert _to_magnitude("1.81B") == 1_810_000_000.0


def test_to_magnitude_millions():
    assert _to_magnitude("824.08M") == 824_080_000.0


def test_to_magnitude_thousands():
    assert _to_magnitude("350K") == 350_000.0


def test_to_magnitude_plain_number():
    assert _to_magnitude("123") == 123.0


def test_to_magnitude_with_separator():
    assert _to_magnitude("1,234M") == 1_234_000_000.0


def test_to_magnitude_negative():
    assert _to_magnitude("-2.5B") == -2_500_000_000.0


def test_to_magnitude_dash_returns_none():
    assert _to_magnitude("--") is None


def test_to_magnitude_none_returns_none():
    assert _to_magnitude(None) is None


def test_to_magnitude_garbage_returns_none():
    assert _to_magnitude("foo") is None
```

- [ ] **Step 10: Run new tests, verify they fail**

Run: `uv run pytest tests/test_yahoo_scraper_converters.py -v -k to_magnitude`
Expected: FAIL — `_to_magnitude` not defined.

- [ ] **Step 11: Add `_to_magnitude` to `app/services/yahoo_scraper.py`**

Append to `app/services/yahoo_scraper.py`:

```python
_MAGNITUDE_SUFFIXES = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def _to_magnitude(s: str | None) -> float | None:
    """Parse `1.81B`, `824.08M`, `350K`, `123` -> raw float dollars. `--` -> None."""
    if s is None:
        return None
    cleaned = s.strip().replace(",", "")
    if not cleaned or cleaned == "--":
        return None
    multiplier = 1.0
    last = cleaned[-1].upper()
    if last in _MAGNITUDE_SUFFIXES:
        multiplier = _MAGNITUDE_SUFFIXES[last]
        cleaned = cleaned[:-1]
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return None
```

- [ ] **Step 12: Run all converter tests, verify they pass**

Run: `uv run pytest tests/test_yahoo_scraper_converters.py -v`
Expected: PASS for all 24 tests.

- [ ] **Step 13: Commit**

```bash
git add app/services/yahoo_scraper.py tests/test_yahoo_scraper_converters.py
git commit -m "scraper: add value converters for float, percent, and magnitude strings"
```

---

## Task 4: Capture LULU HTML fixture and add a parse-fixture smoke test

**Files:**
- Create: `tests/fixtures/lulu_key_statistics.html`
- Create: `tests/test_yahoo_scraper_parse.py`

This task is the bridge between "we have working converters" and "we have a working parser". The fixture is a real HTML page captured one time and committed; future parse tests run offline against it.

- [ ] **Step 1: Make the fixtures directory**

Run: `mkdir -p tests/fixtures`
Expected: directory exists (no error).

- [ ] **Step 2: Capture the LULU Key Statistics page**

Run:
```bash
uv run python -c "
import httpx
r = httpx.get(
    'https://finance.yahoo.com/quote/LULU/key-statistics/?guccounter=1',
    headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    },
    timeout=15,
    follow_redirects=True,
)
print('status:', r.status_code, 'size:', len(r.text))
open('tests/fixtures/lulu_key_statistics.html', 'w').write(r.text)
"
```
Expected: `status: 200 size: <some number > 100000>`

If status is 429 or 403, retry once. If it persists, ask the user before continuing — Yahoo may be temporarily blocking the network the engineer is on.

- [ ] **Step 3: Eyeball the fixture for sanity**

Run: `uv run python -c "html = open('tests/fixtures/lulu_key_statistics.html').read(); print('Forward P/E found:', 'Forward P/E' in html); print('PEG Ratio found:', 'PEG Ratio' in html)"`
Expected: both `True`. If `False`, the page structure changed or Yahoo served a captcha page — stop and investigate.

- [ ] **Step 4: Write a single failing smoke test for the fixture-based parser**

Create `tests/test_yahoo_scraper_parse.py`:

```python
from pathlib import Path

import pytest

from app.services.yahoo_scraper import _parse_document

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "lulu_key_statistics.html"


@pytest.fixture
def lulu_html() -> str:
    return FIXTURE_PATH.read_text()


def test_parse_document_returns_metrics_with_ticker(lulu_html):
    metrics = _parse_document(lulu_html, "LULU")
    assert metrics is not None
    assert metrics.ticker == "LULU"
```

- [ ] **Step 5: Run the test, verify it fails**

Run: `uv run pytest tests/test_yahoo_scraper_parse.py -v`
Expected: FAIL — `_parse_document` not defined.

- [ ] **Step 6: Add a stub `_parse_document` to make the smoke test pass**

Append to `app/services/yahoo_scraper.py`:

```python
from selectolax.parser import HTMLParser

from app.models.schemas import QuarterlyValuation, StockMetrics


def _parse_document(html: str, ticker: str) -> StockMetrics | None:
    """Parse a Yahoo Key Statistics HTML page into a StockMetrics.

    Returns None on hard parse failure (root element missing).
    Returns a partial StockMetrics with None-filled fields when individual
    sections are missing.
    """
    try:
        doc = HTMLParser(html)
    except Exception:
        return None
    if doc.body is None:
        return None
    return StockMetrics(ticker=ticker)
```

- [ ] **Step 7: Run the smoke test, verify it passes**

Run: `uv run pytest tests/test_yahoo_scraper_parse.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add tests/fixtures/lulu_key_statistics.html tests/test_yahoo_scraper_parse.py app/services/yahoo_scraper.py
git commit -m "scraper: add LULU HTML fixture and parser scaffold"
```

---

## Task 5: Implement flat-table parsing (`_parse_stat_table`) and label maps

**Files:**
- Modify: `app/services/yahoo_scraper.py`
- Modify: `tests/test_yahoo_scraper_parse.py`

The Yahoo Key Statistics page has several flat tables (Profitability, Management Effectiveness, Income Statement, Balance Sheet, Cash Flow Statement, Stock Price History, Dividends & Splits). Each is a 2-column table: label, value. Each label maps to one `StockMetrics` field via a dict.

- [ ] **Step 1: Inspect the fixture structure once to confirm table layout**

Run:
```bash
uv run python -c "
from selectolax.parser import HTMLParser
html = open('tests/fixtures/lulu_key_statistics.html').read()
doc = HTMLParser(html)
# Find rows that look like 'label / value' pairs
for tr in doc.css('table tr')[:30]:
    cells = [c.text(strip=True) for c in tr.css('td')]
    if len(cells) == 2:
        print(cells)
"
```
Expected: prints rows like `['Profit Margin', '14.22%']`, `['Operating Margin (ttm)', '19.90%']`, etc. This confirms the page structure. If you see `[]` or different shapes, stop and reinspect — Yahoo may have changed the markup.

Note for the implementer: the actual selector may need adjustment (e.g. some sections live inside `<section>` rather than `<table>`). Use the inspection above to find the right CSS selector. The plan below assumes the canonical 2-cell-per-row pattern.

- [ ] **Step 2: Write a failing test asserting one row from each flat section is parsed for LULU**

Append to `tests/test_yahoo_scraper_parse.py`:

```python
def test_parse_document_extracts_profitability(lulu_html):
    m = _parse_document(lulu_html, "LULU")
    # These exact values were captured from the fixture on 2026-04-11.
    # Update them if the fixture is regenerated.
    assert m.profit_margin == pytest.approx(0.1422, abs=1e-4)
    assert m.operating_margin == pytest.approx(0.199, abs=1e-3)


def test_parse_document_extracts_management(lulu_html):
    m = _parse_document(lulu_html, "LULU")
    assert m.roe is not None
    assert m.roa is not None


def test_parse_document_extracts_income_statement(lulu_html):
    m = _parse_document(lulu_html, "LULU")
    assert m.revenue_growth_yoy is not None
    assert m.earnings_growth_yoy is not None


def test_parse_document_extracts_balance_sheet(lulu_html):
    m = _parse_document(lulu_html, "LULU")
    assert m.debt_to_equity is not None
    assert m.current_ratio is not None
    assert m.total_cash is not None
    assert m.total_debt is not None


def test_parse_document_extracts_cash_flow(lulu_html):
    m = _parse_document(lulu_html, "LULU")
    assert m.operating_cash_flow is not None
    assert m.levered_free_cash_flow is not None


def test_parse_document_extracts_beta_and_dividend(lulu_html):
    m = _parse_document(lulu_html, "LULU")
    assert m.beta is not None
    # forward_dividend_yield and payout_ratio may be None for LULU (no dividend);
    # the assertion is that parsing didn't crash and the field is set.
    assert hasattr(m, "forward_dividend_yield")
```

The parse test for `profit_margin` and `operating_margin` is a hard-coded expected value. **Before running**, confirm the values in the fixture by running:

```bash
uv run python -c "
import re
html = open('tests/fixtures/lulu_key_statistics.html').read()
for pattern in ['Profit Margin', 'Operating Margin']:
    m = re.search(rf'{pattern}.*?(-?\\d+\\.\\d+%)', html)
    print(pattern, '->', m.group(1) if m else 'NOT FOUND')
"
```

If the fixture's profit margin is something other than `14.22%`, **update the assertion in the test to match** before running it. The test should fail because the parser is a stub, NOT because the expected value is wrong.

- [ ] **Step 3: Run the new tests, verify they fail**

Run: `uv run pytest tests/test_yahoo_scraper_parse.py -v`
Expected: FAIL — current `_parse_document` returns an empty `StockMetrics`, all field assertions fail.

- [ ] **Step 4: Add label maps and `_parse_stat_table` to `yahoo_scraper.py`**

Edit `app/services/yahoo_scraper.py`. Above the `_parse_document` function, add:

```python
# Each map: { exact label string : (StockMetrics field name, converter) }
_PROFITABILITY_MAP: dict[str, tuple[str, callable]] = {
    "Profit Margin":          ("profit_margin", _to_percent),
    "Operating Margin (ttm)": ("operating_margin", _to_percent),
}

_MANAGEMENT_MAP: dict[str, tuple[str, callable]] = {
    "Return on Assets (ttm)": ("roa", _to_percent),
    "Return on Equity (ttm)": ("roe", _to_percent),
}

_INCOME_MAP: dict[str, tuple[str, callable]] = {
    "Quarterly Revenue Growth (yoy)":  ("revenue_growth_yoy", _to_percent),
    "Quarterly Earnings Growth (yoy)": ("earnings_growth_yoy", _to_percent),
}

_BALANCE_SHEET_MAP: dict[str, tuple[str, callable]] = {
    "Total Cash (mrq)":        ("total_cash",     _to_magnitude),
    "Total Debt (mrq)":        ("total_debt",     _to_magnitude),
    "Total Debt/Equity (mrq)": ("debt_to_equity", _to_percent),
    "Current Ratio (mrq)":     ("current_ratio",  _to_float),
}

_CASHFLOW_MAP: dict[str, tuple[str, callable]] = {
    "Operating Cash Flow (ttm)":    ("operating_cash_flow",    _to_magnitude),
    "Levered Free Cash Flow (ttm)": ("levered_free_cash_flow", _to_magnitude),
}

_PRICE_HISTORY_MAP: dict[str, tuple[str, callable]] = {
    "Beta (5Y Monthly)": ("beta", _to_float),
}

_DIVIDEND_MAP: dict[str, tuple[str, callable]] = {
    "Forward Annual Dividend Yield 4": ("forward_dividend_yield", _to_percent),
    "Payout Ratio 4":                  ("payout_ratio",           _to_percent),
}

_ALL_FLAT_MAPS: list[dict[str, tuple[str, callable]]] = [
    _PROFITABILITY_MAP,
    _MANAGEMENT_MAP,
    _INCOME_MAP,
    _BALANCE_SHEET_MAP,
    _CASHFLOW_MAP,
    _PRICE_HISTORY_MAP,
    _DIVIDEND_MAP,
]


def _parse_stat_rows(doc: HTMLParser) -> dict[str, str]:
    """Walk every 2-cell row in the document, returning {label: raw_value_string}.

    Some Yahoo labels include footnote markers like the "4" in
    "Forward Annual Dividend Yield 4" — those are part of the label string and
    are matched verbatim by the dispatch maps.
    """
    rows: dict[str, str] = {}
    for tr in doc.css("tr"):
        cells = tr.css("td")
        if len(cells) != 2:
            continue
        label = cells[0].text(strip=True)
        value = cells[1].text(strip=True)
        if label and label not in rows:
            rows[label] = value
    return rows


def _apply_flat_maps(rows: dict[str, str]) -> dict[str, float | None]:
    """Apply every label map to the parsed rows. Returns a dict of
    StockMetrics field name -> parsed value (or None)."""
    out: dict[str, float | None] = {}
    for label_map in _ALL_FLAT_MAPS:
        for label, (field, converter) in label_map.items():
            if label in rows:
                out[field] = converter(rows[label])
    return out
```

- [ ] **Step 5: Update `_parse_document` to apply the flat maps**

In `app/services/yahoo_scraper.py`, replace the `_parse_document` body with:

```python
def _parse_document(html: str, ticker: str) -> StockMetrics | None:
    try:
        doc = HTMLParser(html)
    except Exception:
        return None
    if doc.body is None:
        return None

    rows = _parse_stat_rows(doc)
    flat_fields = _apply_flat_maps(rows)

    return StockMetrics(ticker=ticker, **flat_fields)
```

- [ ] **Step 6: Run the parse tests, verify they pass**

Run: `uv run pytest tests/test_yahoo_scraper_parse.py -v`
Expected: PASS

If a particular field is `None` when it shouldn't be, the most likely cause is that the label string in the dispatch map doesn't exactly match what Yahoo renders (a stray space, a different footnote marker, etc.). Inspect with:

```bash
uv run python -c "
from app.services.yahoo_scraper import _parse_stat_rows
from selectolax.parser import HTMLParser
html = open('tests/fixtures/lulu_key_statistics.html').read()
rows = _parse_stat_rows(HTMLParser(html))
for k in sorted(rows.keys()):
    print(repr(k), '->', repr(rows[k]))
"
```

Adjust the label keys in `_ALL_FLAT_MAPS` until they match the inspected output exactly.

- [ ] **Step 7: Run the full converter + parse test suite**

Run: `uv run pytest tests/test_yahoo_scraper_converters.py tests/test_yahoo_scraper_parse.py -v`
Expected: PASS for all tests.

- [ ] **Step 8: Commit**

```bash
git add app/services/yahoo_scraper.py tests/test_yahoo_scraper_parse.py
git commit -m "scraper: parse flat statistics tables via label dispatch"
```

---

## Task 6: Implement valuation table parsing (`_parse_valuation_table`)

**Files:**
- Modify: `app/services/yahoo_scraper.py`
- Modify: `tests/test_yahoo_scraper_parse.py`

The Valuation Measures table is a 7-column grid: a label cell plus "Current" plus 5 historical period columns. It powers both the top-level snapshot fields (forward_pe, peg_ratio, etc.) and the `valuation_history` list.

- [ ] **Step 1: Inspect the valuation table structure in the fixture**

Run:
```bash
uv run python -c "
from selectolax.parser import HTMLParser
html = open('tests/fixtures/lulu_key_statistics.html').read()
doc = HTMLParser(html)
# Yahoo's valuation table has more than 2 cells per row.
# Find rows with 7 cells (1 label + 6 period columns).
for tr in doc.css('tr'):
    cells = [c.text(strip=True) for c in tr.css('td')]
    if len(cells) >= 6:
        print(cells)
" | head -20
```
Expected: prints something like:
```
['Market Cap', '8.24B', '8.10B', '9.50B', ...]
['Enterprise Value', '...', ...]
['Trailing P/E', '18.50', ...]
['Forward P/E', '13.00', ...]
['PEG Ratio (5yr expected)', '0.90', ...]
['Price/Sales (ttm)', '5.10', ...]
['Price/Book (mrq)', '4.20', ...]
['Enterprise Value/Revenue', '4.80', ...]
['Enterprise Value/EBITDA', '11.30', ...]
```

Also check the header row that gives the period labels:
```bash
uv run python -c "
from selectolax.parser import HTMLParser
html = open('tests/fixtures/lulu_key_statistics.html').read()
doc = HTMLParser(html)
for tr in doc.css('tr'):
    th_cells = [c.text(strip=True) for c in tr.css('th')]
    if len(th_cells) >= 6:
        print('HEADER:', th_cells); break
"
```
Expected: `HEADER: ['', 'Current', '12/31/2025', '9/30/2025', ...]` or similar.

If neither inspection produces the expected output, the page may use a different markup pattern (e.g. labels in `<th>` instead of the first `<td>`). Adjust the parsing CSS selectors below to match.

- [ ] **Step 2: Write failing tests for valuation parsing**

Append to `tests/test_yahoo_scraper_parse.py`:

```python
def test_parse_document_extracts_valuation_snapshot(lulu_html):
    m = _parse_document(lulu_html, "LULU")
    assert m.market_cap is not None
    assert m.enterprise_value is not None
    assert m.trailing_pe is not None
    assert m.forward_pe is not None
    # PEG was the headline reliability bug — must be parsed for LULU.
    assert m.peg_ratio is not None
    assert m.peg_ratio == pytest.approx(0.90, abs=0.05)
    assert m.price_to_sales is not None
    assert m.price_to_book is not None
    assert m.ev_to_revenue is not None
    assert m.ev_to_ebitda is not None


def test_parse_document_populates_valuation_history(lulu_html):
    m = _parse_document(lulu_html, "LULU")
    assert len(m.valuation_history) >= 2
    # First entry must be the "Current" snapshot.
    assert m.valuation_history[0].period == "Current"
    # Top-level forward_pe should equal valuation_history[0].forward_pe
    assert m.forward_pe == m.valuation_history[0].forward_pe
    # At least one historical entry must have a forward_pe value.
    historical = [q for q in m.valuation_history if q.period != "Current"]
    assert any(q.forward_pe is not None for q in historical)
```

**Before running**, confirm the actual PEG value in the fixture and update the assertion if it differs from `0.90`:

```bash
uv run python -c "
import re
html = open('tests/fixtures/lulu_key_statistics.html').read()
m = re.search(r'PEG Ratio.*?(-?\\d+\\.\\d+)', html)
print('PEG in fixture:', m.group(1) if m else 'NOT FOUND')
"
```

- [ ] **Step 3: Run the tests, verify they fail**

Run: `uv run pytest tests/test_yahoo_scraper_parse.py -v -k valuation`
Expected: FAIL — `valuation_history` is empty and snapshot fields are None.

- [ ] **Step 4: Add the valuation map and `_parse_valuation_table`**

Edit `app/services/yahoo_scraper.py`. Above `_parse_document`, add:

```python
# Maps a Yahoo valuation row label to (StockMetrics field, QuarterlyValuation field).
# The same converter (_to_magnitude for $ figures, _to_float for ratios) is used
# for both the snapshot and the history columns.
_VALUATION_MAP: dict[str, tuple[str, callable]] = {
    "Market Cap":               ("market_cap",        _to_magnitude),
    "Enterprise Value":         ("enterprise_value",  _to_magnitude),
    "Trailing P/E":             ("trailing_pe",       _to_float),
    "Forward P/E":              ("forward_pe",        _to_float),
    "PEG Ratio (5yr expected)": ("peg_ratio",         _to_float),
    "Price/Sales (ttm)":        ("price_to_sales",    _to_float),
    "Price/Book (mrq)":         ("price_to_book",     _to_float),
    "Enterprise Value/Revenue": ("ev_to_revenue",     _to_float),
    "Enterprise Value/EBITDA":  ("ev_to_ebitda",      _to_float),
}


def _parse_valuation_table(
    doc: HTMLParser,
) -> tuple[dict[str, float | None], list[QuarterlyValuation]]:
    """Parse the Valuation Measures table.

    Returns:
        snapshot: dict of StockMetrics field -> value from the "Current" column
        history:  list of QuarterlyValuation, one per period column (including "Current")
    """
    # Find the header row that defines the period column labels.
    period_labels: list[str] = []
    for tr in doc.css("tr"):
        th_cells = tr.css("th")
        if len(th_cells) >= 6:
            period_labels = [c.text(strip=True) for c in th_cells[1:]]
            break

    if not period_labels:
        return {}, []

    # Build one QuarterlyValuation per period.
    histories: list[QuarterlyValuation] = [
        QuarterlyValuation(period=p) for p in period_labels
    ]

    snapshot: dict[str, float | None] = {}

    for tr in doc.css("tr"):
        cells = tr.css("td")
        # Valuation rows: 1 label cell + N value cells matching period_labels.
        if len(cells) != 1 + len(period_labels):
            continue
        label = cells[0].text(strip=True)
        if label not in _VALUATION_MAP:
            continue
        stock_field, converter = _VALUATION_MAP[label]
        valuation_field = stock_field  # field names match between StockMetrics and QuarterlyValuation
        for idx, value_cell in enumerate(cells[1:]):
            parsed = converter(value_cell.text(strip=True))
            setattr(histories[idx], valuation_field, parsed)
            if idx == 0:
                # First column is "Current" — also seed the snapshot dict.
                snapshot[stock_field] = parsed

    return snapshot, histories
```

- [ ] **Step 5: Wire `_parse_valuation_table` into `_parse_document`**

In `app/services/yahoo_scraper.py`, update `_parse_document` to:

```python
def _parse_document(html: str, ticker: str) -> StockMetrics | None:
    try:
        doc = HTMLParser(html)
    except Exception:
        return None
    if doc.body is None:
        return None

    rows = _parse_stat_rows(doc)
    flat_fields = _apply_flat_maps(rows)

    snapshot, history = _parse_valuation_table(doc)
    # Snapshot wins over flat parsing for any overlapping field
    # (none currently overlap, but defensive).
    flat_fields.update(snapshot)

    return StockMetrics(
        ticker=ticker,
        valuation_history=history,
        **flat_fields,
    )
```

- [ ] **Step 6: Run the parse tests, verify they pass**

Run: `uv run pytest tests/test_yahoo_scraper_parse.py -v`
Expected: PASS for all parse tests.

If valuation snapshot fields are still `None`, the most likely cause is that `_VALUATION_MAP` keys don't match Yahoo's exact label strings. Inspect with:

```bash
uv run python -c "
from selectolax.parser import HTMLParser
html = open('tests/fixtures/lulu_key_statistics.html').read()
doc = HTMLParser(html)
seen = set()
for tr in doc.css('tr'):
    cells = tr.css('td')
    if len(cells) >= 6:
        seen.add(repr(cells[0].text(strip=True)))
for s in sorted(seen):
    print(s)
"
```

Update label keys in `_VALUATION_MAP` to exactly match what's printed.

- [ ] **Step 7: Commit**

```bash
git add app/services/yahoo_scraper.py tests/test_yahoo_scraper_parse.py
git commit -m "scraper: parse valuation table snapshot and 5-quarter history"
```

---

## Task 7: Implement public `fetch()` with httpx and pytest-httpx

**Files:**
- Modify: `app/services/yahoo_scraper.py`
- Create: `tests/test_yahoo_scraper_fetch.py`

- [ ] **Step 1: Write failing tests for `fetch()` using pytest-httpx mocks**

Create `tests/test_yahoo_scraper_fetch.py`:

```python
from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.services.yahoo_scraper import _URL_TEMPLATE, fetch

FIXTURE = (Path(__file__).parent / "fixtures" / "lulu_key_statistics.html").read_text()


def test_fetch_returns_metrics_on_200(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=_URL_TEMPLATE.format(ticker="LULU"),
        text=FIXTURE,
        status_code=200,
    )
    metrics = fetch("LULU")
    assert metrics is not None
    assert metrics.ticker == "LULU"
    assert metrics.peg_ratio is not None
    assert len(metrics.valuation_history) >= 2


def test_fetch_returns_none_on_503(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=_URL_TEMPLATE.format(ticker="LULU"),
        status_code=503,
    )
    assert fetch("LULU") is None


def test_fetch_returns_none_on_timeout(httpx_mock: HTTPXMock):
    httpx_mock.add_exception(httpx.ReadTimeout("timed out"))
    assert fetch("LULU") is None


def test_fetch_returns_none_on_connect_error(httpx_mock: HTTPXMock):
    httpx_mock.add_exception(httpx.ConnectError("no route"))
    assert fetch("LULU") is None


def test_fetch_returns_partial_when_section_removed(httpx_mock: HTTPXMock):
    # Remove the entire Profitability section by deleting one of its row labels.
    # The parser should still produce a StockMetrics with that field as None
    # while other fields populate normally.
    broken = FIXTURE.replace("Profit Margin", "REMOVED_LABEL")
    httpx_mock.add_response(
        url=_URL_TEMPLATE.format(ticker="LULU"),
        text=broken,
        status_code=200,
    )
    metrics = fetch("LULU")
    assert metrics is not None
    assert metrics.profit_margin is None
    # Operating margin still parses (different label).
    assert metrics.operating_margin is not None
```

- [ ] **Step 2: Run new tests, verify they fail**

Run: `uv run pytest tests/test_yahoo_scraper_fetch.py -v`
Expected: FAIL — `_URL_TEMPLATE` and `fetch` are not defined.

- [ ] **Step 3: Implement `fetch()` and module-level constants in `yahoo_scraper.py`**

At the top of `app/services/yahoo_scraper.py`, just below the existing `from __future__ import annotations`, add:

```python
import logging

import httpx

logger = logging.getLogger(__name__)

_URL_TEMPLATE = "https://finance.yahoo.com/quote/{ticker}/key-statistics/?guccounter=1"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
_TIMEOUT = 10.0  # seconds

_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    """Lazily build and reuse one module-level httpx Client.

    Lazy creation lets pytest-httpx intercept calls in tests without needing
    to monkeypatch a pre-instantiated client.
    """
    global _client
    if _client is None:
        _client = httpx.Client(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True)
    return _client
```

At the bottom of `app/services/yahoo_scraper.py`, add:

```python
def _fetch_html(ticker: str) -> str | None:
    """Fetch the raw HTML for one ticker. Returns None on any failure."""
    url = _URL_TEMPLATE.format(ticker=ticker)
    try:
        response = _get_client().get(url)
    except httpx.HTTPError as exc:
        logger.warning("yahoo_scraper: HTTP error fetching %s: %s", ticker, exc)
        return None
    if response.status_code != 200:
        logger.warning(
            "yahoo_scraper: non-200 (%s) fetching %s",
            response.status_code,
            ticker,
        )
        return None
    return response.text


def fetch(ticker: str) -> StockMetrics | None:
    """Fetch and parse the Yahoo Key Statistics page for one ticker.

    Returns None on hard failure (network, non-200, unparseable document).
    Returns a partial StockMetrics with None-filled fields when individual
    sections are missing or unparseable.
    """
    html = _fetch_html(ticker)
    if html is None:
        return None
    try:
        return _parse_document(html, ticker)
    except Exception as exc:
        logger.warning("yahoo_scraper: parse failed for %s: %s", ticker, exc)
        return None
```

- [ ] **Step 4: Run fetch tests, verify they pass**

Run: `uv run pytest tests/test_yahoo_scraper_fetch.py -v`
Expected: PASS for all 5 tests.

- [ ] **Step 5: Run the full scraper test suite**

Run: `uv run pytest tests/test_yahoo_scraper_converters.py tests/test_yahoo_scraper_parse.py tests/test_yahoo_scraper_fetch.py -v`
Expected: PASS for everything.

- [ ] **Step 6: Commit**

```bash
git add app/services/yahoo_scraper.py tests/test_yahoo_scraper_fetch.py
git commit -m "scraper: implement public fetch() with httpx client and error handling"
```

---

## Task 8: Wire the scraper into `stock_service.get_stock_metrics`

**Files:**
- Modify: `app/services/stock_service.py`
- Modify: `tests/test_stock_service.py`

`get_stock_info` and `validate_tickers` keep using yfinance. Only `get_stock_metrics` switches to the scraper.

- [ ] **Step 1: Read the existing `tests/test_stock_service.py`**

Done in this session (see earlier turn). The two `get_stock_metrics` tests reference legacy fields (`revenueGrowth`, `earningsGrowth`, etc.) and patch `app.services.stock_service.yf.Ticker`. They will be replaced because the function no longer goes through yfinance for metrics.

- [ ] **Step 2: Replace the two existing `get_stock_metrics` tests with new ones**

In `tests/test_stock_service.py`, delete the two functions `test_get_stock_metrics_populates_fields` and `test_get_stock_metrics_missing_fields_become_none`. Add at the end of the file:

```python
from app.models.schemas import StockMetrics, QuarterlyValuation


@patch("app.services.stock_service.yahoo_scraper.fetch")
def test_get_stock_metrics_delegates_to_scraper(mock_fetch):
    mock_fetch.return_value = StockMetrics(
        ticker="LULU",
        forward_pe=13.0,
        peg_ratio=0.90,
        valuation_history=[
            QuarterlyValuation(period="Current", forward_pe=13.0),
            QuarterlyValuation(period="12/31/2025", forward_pe=15.0),
        ],
    )
    m = get_stock_metrics("LULU")
    assert m is not None
    assert m.ticker == "LULU"
    assert m.forward_pe == 13.0
    assert m.peg_ratio == 0.90
    assert len(m.valuation_history) == 2
    mock_fetch.assert_called_once_with("LULU")


@patch("app.services.stock_service.yahoo_scraper.fetch")
def test_get_stock_metrics_returns_none_when_scraper_fails(mock_fetch):
    mock_fetch.return_value = None
    assert get_stock_metrics("BOGUS") is None
```

- [ ] **Step 3: Run new tests, verify they fail**

Run: `uv run pytest tests/test_stock_service.py -v -k stock_metrics`
Expected: FAIL — `app.services.stock_service` does not import `yahoo_scraper`.

- [ ] **Step 4: Replace `get_stock_metrics` body in `stock_service.py`**

Edit `app/services/stock_service.py`. At the top of the file, after the existing `import yfinance as yf` line, add:

```python
from app.services import yahoo_scraper
```

Then replace the entire `get_stock_metrics` function body with:

```python
def get_stock_metrics(ticker: str) -> StockMetrics | None:
    """Fetch all scoring metrics for one ticker via the Yahoo HTML scraper.

    Step 1 (`validate_tickers`, `get_stock_info`) still uses yfinance because
    it's faster for the existence-check use case. Step 3's full metrics fetch
    uses the scraper to get reliable PEG, historical valuation, and
    same-snapshot pricing across peers.
    """
    return yahoo_scraper.fetch(ticker)
```

- [ ] **Step 5: Run new tests, verify they pass**

Run: `uv run pytest tests/test_stock_service.py -v -k stock_metrics`
Expected: PASS

- [ ] **Step 6: Run the full `test_stock_service.py` to ensure the yfinance-backed tests still work**

Run: `uv run pytest tests/test_stock_service.py -v`
Expected: PASS for all tests in the file.

- [ ] **Step 7: Commit**

```bash
git add app/services/stock_service.py tests/test_stock_service.py
git commit -m "stock_service: route get_stock_metrics through yahoo_scraper"
```

---

## Task 9: Refactor `score_category` into `score_category_single` and add composite scoring

**Files:**
- Modify: `app/services/scoring_service.py`
- Modify: `tests/test_scoring_service.py`

This is the structural change that lets a category score multiple sub-metrics. After this task, the existing categories still work (via `score_category_single`), but the public `score_category(category, stocks)` function now dispatches to either `_score_composite` or a derived scorer.

- [ ] **Step 1: Write failing tests for `score_category_single`**

Append to `tests/test_scoring_service.py`:

```python
from app.services.scoring_service import score_category_single


def test_score_category_single_lower_better():
    stocks = [
        _metrics("A", forward_pe=10.0),
        _metrics("B", forward_pe=20.0),
        _metrics("C", forward_pe=30.0),
    ]
    scores = score_category_single(stocks, "forward_pe", "lower")
    assert scores["A"].score == 5
    assert scores["B"].score == 3
    assert scores["C"].score == 1


def test_score_category_single_higher_better():
    stocks = [
        _metrics("A", roe=0.10),
        _metrics("B", roe=0.20),
        _metrics("C", roe=0.30),
    ]
    scores = score_category_single(stocks, "roe", "higher")
    assert scores["A"].score == 1
    assert scores["C"].score == 5


def test_score_category_single_handles_missing():
    stocks = [
        _metrics("A", forward_pe=10.0),
        _metrics("B", forward_pe=None),
    ]
    scores = score_category_single(stocks, "forward_pe", "lower")
    assert scores["A"].score == 5
    assert scores["B"].score == 3  # missing -> neutral
```

- [ ] **Step 2: Run new tests, verify they fail**

Run: `uv run pytest tests/test_scoring_service.py -v -k score_category_single`
Expected: FAIL — `score_category_single` not defined. Also expect: existing tests in this file are still failing because they reference the old `revenue_growth` / `eps_growth` / `dividend_yield` fields. We'll fix all of these in the same task.

- [ ] **Step 3: Replace `app/services/scoring_service.py` end-to-end**

Replace the entire contents of `app/services/scoring_service.py` with:

```python
from itertools import groupby
from statistics import mean

from app.models.schemas import CategoryScore, StockMetrics, StockRanking

CATEGORIES = [
    "valuation",
    "growth",
    "profitability",
    "capital_efficiency",
    "health",
    "cash_quality",
    "valuation_trend",
    "dividend",
]

DEFAULT_WEIGHTS: dict[str, float] = {
    "valuation":          0.18,
    "growth":             0.18,
    "profitability":      0.14,
    "capital_efficiency": 0.12,
    "health":             0.12,
    "cash_quality":       0.12,
    "valuation_trend":    0.08,
    "dividend":           0.06,
}

# Sub-metrics for each composite category: (StockMetrics field, "lower"|"higher").
# `cash_quality` and `valuation_trend` are derived metrics handled separately.
_CATEGORY_SUBMETRICS: dict[str, list[tuple[str, str]]] = {
    "valuation":          [("forward_pe", "lower"), ("peg_ratio", "lower"), ("ev_to_ebitda", "lower")],
    "growth":             [("revenue_growth_yoy", "higher"), ("earnings_growth_yoy", "higher")],
    "profitability":      [("operating_margin", "higher"), ("profit_margin", "higher")],
    "capital_efficiency": [("roe", "higher"), ("roa", "higher")],
    "health":             [("debt_to_equity", "lower"), ("current_ratio", "higher")],
    "dividend":           [("forward_dividend_yield", "higher")],
}


def _format_value(field: str, raw: float | None) -> str:
    """Format a single sub-metric value for display in CategoryScore.display."""
    if raw is None:
        return "—"
    if field in ("forward_pe", "trailing_pe", "ev_to_ebitda", "ev_to_revenue",
                 "price_to_sales", "price_to_book", "peg_ratio", "current_ratio", "beta"):
        return f"{raw:.2f}"
    if field in ("debt_to_equity", "operating_margin", "profit_margin", "roe", "roa",
                 "revenue_growth_yoy", "earnings_growth_yoy", "forward_dividend_yield",
                 "payout_ratio"):
        return f"{raw * 100:.1f}%"
    return f"{raw}"


def score_category_single(
    stocks: list[StockMetrics],
    field: str,
    direction: str,
) -> dict[str, CategoryScore]:
    """Score each stock 1-5 by relative ranking on a single field.

    Returns a dict ticker -> CategoryScore. Missing values get neutral 3.
    Equal raw values share the same score.
    """
    values: list[tuple[str, float]] = []
    missing: list[str] = []
    for stock in stocks:
        raw = getattr(stock, field)
        if raw is None:
            missing.append(stock.ticker)
        else:
            values.append((stock.ticker, float(raw)))

    result: dict[str, CategoryScore] = {}

    if not values:
        for stock in stocks:
            result[stock.ticker] = CategoryScore(
                category=field, score=3, raw_value=None, display="—",
            )
        return result

    if len(values) == 1:
        only_ticker, only_raw = values[0]
        result[only_ticker] = CategoryScore(
            category=field, score=5, raw_value=only_raw,
            display=_format_value(field, only_raw),
        )
    else:
        reverse = direction == "higher"
        sorted_values = sorted(values, key=lambda x: x[1], reverse=reverse)
        groups: list[tuple[float, list[str]]] = []
        for raw_val, group_iter in groupby(sorted_values, key=lambda x: x[1]):
            groups.append((raw_val, [t for t, _ in group_iter]))
        num_groups = len(groups)
        for group_idx, (raw_val, tickers) in enumerate(groups):
            score = 5 if num_groups == 1 else round(5 - (4 * group_idx / (num_groups - 1)))
            for ticker in tickers:
                result[ticker] = CategoryScore(
                    category=field, score=score, raw_value=raw_val,
                    display=_format_value(field, raw_val),
                )

    for ticker in missing:
        result[ticker] = CategoryScore(
            category=field, score=3, raw_value=None, display="—",
        )

    return result


def _score_composite(
    category: str,
    stocks: list[StockMetrics],
    sub_metrics: list[tuple[str, str]],
) -> dict[str, CategoryScore]:
    """Score a composite category as the rounded mean of per-sub-metric scores.

    Display string lists each sub-metric's formatted value, e.g.
    "Rev +22.6%, EPS -22.9%".
    """
    per_sub: list[dict[str, CategoryScore]] = [
        score_category_single(stocks, field, direction)
        for field, direction in sub_metrics
    ]

    result: dict[str, CategoryScore] = {}
    for stock in stocks:
        sub_scores = [d[stock.ticker].score for d in per_sub]
        composite = round(mean(sub_scores))
        # Display: comma-separated formatted sub-values for this stock.
        parts = []
        for (field, _), per_sub_dict in zip(sub_metrics, per_sub):
            cs = per_sub_dict[stock.ticker]
            parts.append(_format_value(field, cs.raw_value))
        result[stock.ticker] = CategoryScore(
            category=category,
            score=composite,
            raw_value=None,  # composite has no single raw value
            display=", ".join(parts),
        )
    return result


def _score_cash_quality(stocks: list[StockMetrics]) -> dict[str, CategoryScore]:
    """Cash Quality = FCF yield (levered_free_cash_flow / market_cap), higher is better."""
    # Stash derived value on a temporary attribute via a parallel list.
    yields: list[tuple[str, float | None]] = []
    for s in stocks:
        if (
            s.levered_free_cash_flow is None
            or s.market_cap is None
            or s.market_cap == 0
        ):
            yields.append((s.ticker, None))
        else:
            yields.append((s.ticker, s.levered_free_cash_flow / s.market_cap))

    # Build proxy StockMetrics carrying the derived field as `forward_dividend_yield`
    # is awkward — instead, sort and rank yields directly.
    valid = [(t, y) for t, y in yields if y is not None]
    missing = [t for t, y in yields if y is None]
    result: dict[str, CategoryScore] = {}

    if not valid:
        for s in stocks:
            result[s.ticker] = CategoryScore(
                category="cash_quality", score=3, raw_value=None, display="—",
            )
        return result

    sorted_y = sorted(valid, key=lambda x: x[1], reverse=True)  # higher yield = better
    groups: list[tuple[float, list[str]]] = []
    for raw, gi in groupby(sorted_y, key=lambda x: x[1]):
        groups.append((raw, [t for t, _ in gi]))
    num_groups = len(groups)
    for idx, (raw, tickers) in enumerate(groups):
        score = 5 if num_groups == 1 else round(5 - (4 * idx / (num_groups - 1)))
        for t in tickers:
            result[t] = CategoryScore(
                category="cash_quality", score=score, raw_value=raw,
                display=f"FCF yield {raw * 100:.1f}%",
            )
    for t in missing:
        result[t] = CategoryScore(
            category="cash_quality", score=3, raw_value=None, display="—",
        )
    return result


def _score_valuation_trend(stocks: list[StockMetrics]) -> dict[str, CategoryScore]:
    """Valuation Trend = current Forward P/E ÷ mean of historical Forward P/E.

    Excludes the "Current" entry from the historical mean. Lower trend ratio
    (cheaper than own history) is better.
    """
    ratios: list[tuple[str, float | None]] = []
    for s in stocks:
        if not s.valuation_history or s.forward_pe is None:
            ratios.append((s.ticker, None))
            continue
        historical = [
            q.forward_pe for q in s.valuation_history
            if q.period != "Current" and q.forward_pe is not None
        ]
        if not historical:
            ratios.append((s.ticker, None))
            continue
        hist_mean = mean(historical)
        if hist_mean == 0:
            ratios.append((s.ticker, None))
            continue
        ratios.append((s.ticker, s.forward_pe / hist_mean))

    valid = [(t, r) for t, r in ratios if r is not None]
    missing = [t for t, r in ratios if r is None]
    result: dict[str, CategoryScore] = {}

    if not valid:
        for s in stocks:
            result[s.ticker] = CategoryScore(
                category="valuation_trend", score=3, raw_value=None, display="—",
            )
        return result

    sorted_r = sorted(valid, key=lambda x: x[1])  # lower ratio = better
    groups: list[tuple[float, list[str]]] = []
    for raw, gi in groupby(sorted_r, key=lambda x: x[1]):
        groups.append((raw, [t for t, _ in gi]))
    num_groups = len(groups)
    for idx, (raw, tickers) in enumerate(groups):
        score = 5 if num_groups == 1 else round(5 - (4 * idx / (num_groups - 1)))
        for t in tickers:
            result[t] = CategoryScore(
                category="valuation_trend", score=score, raw_value=raw,
                display=f"Fwd P/E {raw:.2f}× own avg",
            )
    for t in missing:
        result[t] = CategoryScore(
            category="valuation_trend", score=3, raw_value=None, display="—",
        )
    return result


def score_category(
    category: str,
    stocks: list[StockMetrics],
) -> dict[str, CategoryScore]:
    """Public dispatch: returns one CategoryScore per ticker for the named category."""
    if category == "cash_quality":
        return _score_cash_quality(stocks)
    if category == "valuation_trend":
        return _score_valuation_trend(stocks)
    if category not in _CATEGORY_SUBMETRICS:
        raise ValueError(f"Unknown category: {category}")
    return _score_composite(category, stocks, _CATEGORY_SUBMETRICS[category])


def compute_weighted_scores(
    stocks: list[StockMetrics],
    weights: dict[str, float],
) -> list[StockRanking]:
    """Score every category, apply weights, sort, assign ranks.

    Weights are normalized internally so they always sum to 1.0. Categories
    not present in `weights` get a default of 0.0.
    """
    total = sum(weights.get(cat, 0.0) for cat in CATEGORIES)
    if total <= 0:
        raise ValueError("At least one category weight must be positive.")
    norm = {cat: weights.get(cat, 0.0) / total for cat in CATEGORIES}

    per_category: dict[str, dict[str, CategoryScore]] = {}
    for cat in CATEGORIES:
        per_category[cat] = score_category(cat, stocks)

    rankings: list[StockRanking] = []
    for stock in stocks:
        category_scores = [per_category[cat][stock.ticker] for cat in CATEGORIES]
        weighted = sum(cs.score * norm[cs.category] for cs in category_scores)
        rankings.append(
            StockRanking(
                ticker=stock.ticker,
                category_scores=category_scores,
                weighted_score=round(weighted, 4),
                rank=0,
            )
        )

    rankings.sort(key=lambda r: (-r.weighted_score, r.ticker))
    for idx, r in enumerate(rankings, start=1):
        r.rank = idx

    return rankings
```

- [ ] **Step 4: Run the new `score_category_single` tests**

Run: `uv run pytest tests/test_scoring_service.py -v -k score_category_single`
Expected: PASS

- [ ] **Step 5: Update the existing scoring tests to use new field names**

In `tests/test_scoring_service.py`, replace the `_metrics` helper to match the new `StockMetrics` schema and update tests that reference renamed fields. Replace the existing helper:

```python
def _metrics(ticker: str, **overrides) -> StockMetrics:
    defaults = dict(
        ticker=ticker,
        forward_pe=None, trailing_pe=None, peg_ratio=None,
        price_to_sales=None, price_to_book=None,
        ev_to_revenue=None, ev_to_ebitda=None,
        market_cap=None, enterprise_value=None,
        profit_margin=None, operating_margin=None,
        roe=None, roa=None,
        revenue_growth_yoy=None, earnings_growth_yoy=None,
        debt_to_equity=None, current_ratio=None,
        total_cash=None, total_debt=None,
        operating_cash_flow=None, levered_free_cash_flow=None,
        beta=None,
        forward_dividend_yield=None, payout_ratio=None,
    )
    defaults.update(overrides)
    return StockMetrics(**defaults)
```

Update the existing tests in this file:
- `test_growth_highest_revenue_growth_gets_5`: replace `revenue_growth=0.30` → `revenue_growth_yoy=0.30`, etc.
- `test_compute_weighted_scores_ranks_best_first`: replace `revenue_growth=0.30, operating_margin=0.20, roe=0.30, debt_to_equity=0.20, dividend_yield=0.03` → `revenue_growth_yoy=0.30, operating_margin=0.20, roe=0.30, debt_to_equity=0.20, forward_dividend_yield=0.03`. Also add `peg_ratio` and `ev_to_ebitda` so the new composite valuation category has data: e.g. `forward_pe=10.0, peg_ratio=1.0, ev_to_ebitda=8.0`.
- `test_compute_weighted_scores_weights_change_order`: same renames. Both `val_heavy` and `growth_heavy` weight dicts need to use the new category IDs:

  ```python
  val_heavy = {"valuation": 1.0, "growth": 0.0, "profitability": 0.0,
               "capital_efficiency": 0.0, "health": 0.0, "cash_quality": 0.0,
               "valuation_trend": 0.0, "dividend": 0.0}
  growth_heavy = {"valuation": 0.0, "growth": 1.0, "profitability": 0.0,
                  "capital_efficiency": 0.0, "health": 0.0, "cash_quality": 0.0,
                  "valuation_trend": 0.0, "dividend": 0.0}
  ```
- `test_ties_broken_alphabetically`: use new field names.
- `test_weights_are_normalized_if_not_sum_to_one`: same renames.
- `test_missing_data_gets_neutral_3`, `test_all_missing_all_neutral`, `test_single_stock_gets_5`: these reference `score_category("valuation", ...)`. Valuation is now composite — confirm the same expectations still hold (a single sub-metric present still produces a sensible composite). Update assertions:
  - With one peer: composite score is 5 (only sub-metric available scores 5, mean of [5] = 5). PASS as written.
  - With all-missing: every peer scores 3 on every sub-metric → composite mean is 3. PASS as written.
  - With one missing one present: the missing peer scores 3 for `forward_pe`, but also 3 for `peg_ratio` and `ev_to_ebitda` (no data); the present peer scores 5 for `forward_pe`, 3 for the others (no data) → composite mean = round((5+3+3)/3) = round(3.67) = 4. **This is a behavior change.** Update the test assertion: `scores["A"].score == 4` (was 5), `scores["C"].score == 2` (was 1).
  - In `test_health_lower_debt_equity_better`: health is now composite (debt_to_equity lower + current_ratio higher). The peers in the test only set `debt_to_equity`, so `current_ratio` is None for all → neutral 3 across the board for that sub-metric. Composite mean: `round((debt_score + 3) / 2)`. For A `debt_score=5` → `round(4) = 4`. For C `debt_score=1` → `round(2) = 2`. **Update assertions** to `scores["A"].score == 4` and `scores["C"].score == 2`.
  - In `test_valuation_lowest_pe_gets_5`: same reasoning as `test_missing_data_gets_neutral_3`. With only forward_pe set: A gets `round((5+3+3)/3)=4`, B gets `round((3+3+3)/3)=3`, C gets `round((1+3+3)/3)=2`. **Update assertions:** `scores["A"].score == 4`, `scores["B"].score == 3`, `scores["C"].score == 2`.

- [ ] **Step 6: Run the full scoring test suite**

Run: `uv run pytest tests/test_scoring_service.py -v`
Expected: PASS for all tests (existing + new).

- [ ] **Step 7: Commit**

```bash
git add app/services/scoring_service.py tests/test_scoring_service.py
git commit -m "scoring: refactor to 8 categories with composite and derived scoring"
```

---

## Task 10: Add dedicated tests for derived scorers (Cash Quality and Valuation Trend)

**Files:**
- Create: `tests/test_scoring_derived.py`

These get their own file because the math is non-trivial and worth isolating from the composite tests.

- [ ] **Step 1: Create the test file with failing tests**

Create `tests/test_scoring_derived.py`:

```python
from app.models.schemas import QuarterlyValuation, StockMetrics
from app.services.scoring_service import score_category


def _m(ticker, **kwargs) -> StockMetrics:
    return StockMetrics(ticker=ticker, **kwargs)


def test_cash_quality_higher_fcf_yield_wins():
    stocks = [
        _m("A", levered_free_cash_flow=2_000_000_000, market_cap=10_000_000_000),  # 20% yield
        _m("B", levered_free_cash_flow=500_000_000,   market_cap=10_000_000_000),  # 5% yield
        _m("C", levered_free_cash_flow=100_000_000,   market_cap=10_000_000_000),  # 1% yield
    ]
    scores = score_category("cash_quality", stocks)
    assert scores["A"].score == 5
    assert scores["B"].score == 3
    assert scores["C"].score == 1
    assert "20.0%" in scores["A"].display


def test_cash_quality_missing_market_cap_neutral():
    stocks = [
        _m("A", levered_free_cash_flow=1_000_000_000, market_cap=10_000_000_000),
        _m("B", levered_free_cash_flow=1_000_000_000, market_cap=None),
    ]
    scores = score_category("cash_quality", stocks)
    assert scores["A"].score == 5
    assert scores["B"].score == 3


def test_cash_quality_zero_market_cap_neutral():
    stocks = [
        _m("A", levered_free_cash_flow=1_000_000_000, market_cap=10_000_000_000),
        _m("B", levered_free_cash_flow=1_000_000_000, market_cap=0),
    ]
    scores = score_category("cash_quality", stocks)
    assert scores["B"].score == 3


def test_valuation_trend_cheaper_than_history_wins():
    # A is cheaper than its own history (forward_pe 10 vs avg 20 → ratio 0.5).
    # B is more expensive than its history (forward_pe 30 vs avg 20 → ratio 1.5).
    a = _m(
        "A",
        forward_pe=10.0,
        valuation_history=[
            QuarterlyValuation(period="Current", forward_pe=10.0),
            QuarterlyValuation(period="12/31/2025", forward_pe=18.0),
            QuarterlyValuation(period="9/30/2025", forward_pe=22.0),
        ],
    )
    b = _m(
        "B",
        forward_pe=30.0,
        valuation_history=[
            QuarterlyValuation(period="Current", forward_pe=30.0),
            QuarterlyValuation(period="12/31/2025", forward_pe=18.0),
            QuarterlyValuation(period="9/30/2025", forward_pe=22.0),
        ],
    )
    scores = score_category("valuation_trend", [a, b])
    assert scores["A"].score == 5
    assert scores["B"].score == 1
    # Display references the trend ratio.
    assert "0.50" in scores["A"].display


def test_valuation_trend_excludes_current_from_history_mean():
    # If the parser ever leaks "Current" into the historical mean, ratio for
    # this stock would be 12/((12+18+22)/3) = 12/17.33 = 0.69 (not 0.6).
    # Excluding Current correctly: 12/((18+22)/2) = 12/20 = 0.6.
    a = _m(
        "A",
        forward_pe=12.0,
        valuation_history=[
            QuarterlyValuation(period="Current", forward_pe=12.0),
            QuarterlyValuation(period="12/31/2025", forward_pe=18.0),
            QuarterlyValuation(period="9/30/2025", forward_pe=22.0),
        ],
    )
    scores = score_category("valuation_trend", [a])
    # Single stock → score 5; check the raw_value for the ratio.
    assert scores["A"].raw_value is not None
    assert abs(scores["A"].raw_value - 0.6) < 0.001


def test_valuation_trend_missing_history_neutral():
    a = _m("A", forward_pe=10.0, valuation_history=[])
    b = _m("B", forward_pe=20.0, valuation_history=[
        QuarterlyValuation(period="Current", forward_pe=20.0),
        QuarterlyValuation(period="12/31/2025", forward_pe=10.0),
    ])
    scores = score_category("valuation_trend", [a, b])
    assert scores["A"].score == 3
    assert scores["B"].score == 5


def test_valuation_trend_only_current_in_history_neutral():
    a = _m("A", forward_pe=10.0, valuation_history=[
        QuarterlyValuation(period="Current", forward_pe=10.0),
    ])
    scores = score_category("valuation_trend", [a])
    assert scores["A"].score == 3
```

- [ ] **Step 2: Run the new tests, verify they pass**

Run: `uv run pytest tests/test_scoring_derived.py -v`
Expected: PASS for all 7 tests. The scoring code already implements the derived scorers from Task 9, so no further code changes are needed in this task.

- [ ] **Step 3: Run the full scoring suite**

Run: `uv run pytest tests/test_scoring_service.py tests/test_scoring_derived.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_scoring_derived.py
git commit -m "tests: add dedicated coverage for cash_quality and valuation_trend scorers"
```

---

## Task 11: Update Step 3 UI — grouped tables and Forward P/E trend chart

**Files:**
- Modify: `app/ui/screens/step3_metrics.py`

This step has no automated test — it's UI rendering against Streamlit. Validation is via the manual smoke test at the end.

- [ ] **Step 1: Replace `_METRIC_ROWS` with `_METRIC_GROUPS` in `step3_metrics.py`**

In `app/ui/screens/step3_metrics.py`, replace the existing `_METRIC_ROWS` constant with:

```python
_METRIC_GROUPS: list[tuple[str, list[tuple[str, str, Callable[[float], str]]]]] = [
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
        ("Debt/Equity",   "debt_to_equity", lambda v: f"{v*100:.1f}%"),
        ("Current Ratio", "current_ratio",  lambda v: f"{v:.2f}"),
        ("Total Cash",    "total_cash",     lambda v: f"${v/1e9:.2f}B"),
        ("Total Debt",    "total_debt",     lambda v: f"${v/1e9:.2f}B"),
    ]),
    ("Cash Flow", [
        ("Operating Cash Flow",    "operating_cash_flow",    lambda v: f"${v/1e9:.2f}B"),
        ("Levered Free Cash Flow", "levered_free_cash_flow", lambda v: f"${v/1e9:.2f}B"),
    ]),
    ("Market Context", [
        ("Beta (5Y)",        "beta",             lambda v: f"{v:.2f}"),
        ("Market Cap",       "market_cap",       lambda v: f"${v/1e9:.2f}B"),
        ("Enterprise Value", "enterprise_value", lambda v: f"${v/1e9:.2f}B"),
    ]),
    ("Dividend", [
        ("Forward Dividend Yield", "forward_dividend_yield", lambda v: f"{v*100:.2f}%"),
        ("Payout Ratio",           "payout_ratio",           lambda v: f"{v*100:.1f}%"),
    ]),
]
```

Delete the old `_METRIC_ROWS` constant.

- [ ] **Step 2: Replace the render loop**

In `app/ui/screens/step3_metrics.py`, find the section that builds the dataframe:

```python
st.write("Side-by-side comparison of 12 key metrics.")
```

through to the end of `st.markdown(df.to_html(...))`.

Replace it with:

```python
st.write("Side-by-side comparison of fundamentals from Yahoo Key Statistics.")

for group_name, rows in _METRIC_GROUPS:
    st.markdown(f"#### {group_name}")
    data: dict[str, list[str]] = {"Metric": [r[0] for r in rows]}
    for m in metrics_list:
        data[m.ticker] = [_format(getattr(m, attr), fmt) for _, attr, fmt in rows]
    df = pd.DataFrame(data)
    st.markdown(
        df.to_html(index=False, classes="metrics-table", escape=False),
        unsafe_allow_html=True,
    )

# Forward P/E trend chart (under the Valuation group conceptually,
# rendered after all groups so it has the most space).
_render_forward_pe_trend(metrics_list)
```

Keep the existing CSS injection block above this loop unchanged.

- [ ] **Step 3: Add the trend chart helper**

Above the `render` function in `app/ui/screens/step3_metrics.py`, add:

```python
def _render_forward_pe_trend(metrics_list: list[StockMetrics]) -> None:
    """Render a 5-quarter Forward P/E trend chart, one line per peer.

    Skips silently if no peer has valuation_history or if peers' period
    label lists disagree (different fiscal calendars).
    """
    histories = [m for m in metrics_list if m.valuation_history]
    if not histories:
        return

    reference_periods = [q.period for q in histories[0].valuation_history]
    if any(
        [q.period for q in m.valuation_history] != reference_periods
        for m in histories
    ):
        return  # period mismatch — skip rather than render misleading chart

    chart_data: dict[str, list[float | None]] = {}
    for m in histories:
        chart_data[m.ticker] = [q.forward_pe for q in m.valuation_history]
    trend_df = pd.DataFrame(chart_data, index=reference_periods)

    st.markdown("##### Forward P/E trend (current + last 5 quarters)")
    st.line_chart(trend_df)
```

- [ ] **Step 4: Verify imports are still correct**

The file already imports `pandas as pd`, `streamlit as st`, and `StockMetrics`. No new imports needed. Confirm the file still compiles:

Run: `uv run python -c "from app.ui.screens import step3_metrics; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add app/ui/screens/step3_metrics.py
git commit -m "ui: group Step 3 metrics by section and add Forward P/E trend chart"
```

---

## Task 12: Update Step 4 UI — 8 weight sliders with new labels

**Files:**
- Modify: `app/ui/screens/step4_ranking.py`

- [ ] **Step 1: Replace `_CATEGORY_LABELS` in `step4_ranking.py`**

In `app/ui/screens/step4_ranking.py`, replace the existing `_CATEGORY_LABELS` constant with:

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

- [ ] **Step 2: Verify the slider loop and table render handle 8 categories without code changes**

Read the existing `_render_weight_sliders` and the table-render block. Both iterate over `CATEGORIES` and use `_CATEGORY_LABELS[cs.category]`, so they automatically pick up the new categories. No further code changes are needed in this file.

- [ ] **Step 3: Smoke-test the import**

Run: `uv run python -c "from app.ui.screens import step4_ranking; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add app/ui/screens/step4_ranking.py
git commit -m "ui: relabel Step 4 sliders for 8 scoring categories"
```

---

## Task 13: Update the recommendation agent prompt

**Files:**
- Modify: `app/agents/recommendation_agent.py`
- Modify: `tests/test_recommendation_agent.py` (only if it asserts on prompt content)

- [ ] **Step 1: Inspect existing tests to see what they assert about the agent**

Run: `uv run python -c "import pathlib; print(pathlib.Path('tests/test_recommendation_agent.py').read_text())"` (or use Read tool)
Goal: confirm whether any test pins prompt content. If a test asserts on category names, it must be updated alongside the prompt.

- [ ] **Step 2: Update the agent's `instructions` and prompt copy**

In `app/agents/recommendation_agent.py`, replace the `Agent(...)` `instructions=` block in `_run_agent` with:

```python
instructions=(
    "You are a concise investment analyst. Given a peer ranking and the user's "
    "category weights, write a 2-3 sentence recommendation explaining why the "
    "top stock stands out. Reference specific metric values from the category "
    "scores. The categories are: Valuation (forward P/E, PEG, EV/EBITDA), "
    "Growth (revenue and earnings YoY), Profitability (operating and profit "
    "margin), Capital Efficiency (ROE and ROA), Financial Health (debt/equity "
    "and current ratio), Cash Quality (free cash flow yield), Valuation Trend "
    "(current forward P/E vs the stock's own 5-quarter average), and Dividend "
    "(forward yield). Do NOT give financial advice disclaimers."
),
```

The body of `_format_prompt` already iterates `top.category_scores` generically, so no change to the prompt-construction code is needed.

- [ ] **Step 3: Run the recommendation agent tests**

Run: `uv run pytest tests/test_recommendation_agent.py -v`
Expected: PASS. If any test fails on the category-name change, update the assertion to match the new instructions string.

- [ ] **Step 4: Commit**

```bash
git add app/agents/recommendation_agent.py tests/test_recommendation_agent.py
git commit -m "agent: brief recommendation prompt on the new 8-category model"
```

---

## Task 14: Full test suite + manual end-to-end smoke test

**Files:**
- None (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `uv run pytest -v`
Expected: every test passes. If anything fails, fix it before continuing.

- [ ] **Step 2: Lint check**

Run: `uv run ruff check .`
Expected: no errors. Fix anything reported.

- [ ] **Step 3: Format check**

Run: `uv run ruff format --check .`
Expected: no diffs. Run `uv run ruff format .` and re-commit if needed.

- [ ] **Step 4: Launch the app for manual smoke**

Run: `uv run streamlit run streamlit_app.py`
The browser should open at http://localhost:8501.

- [ ] **Step 5: Manual smoke checklist**

Walk through the wizard:

1. **Step 1:** enter ticker `LULU`. Verify: company name, sector, price load (from yfinance — should be unchanged).
2. **Step 2:** accept the suggested peers (Nike, etc.). Verify peer discovery still works.
3. **Step 3:** verify all 8 metric groups render (Valuation, Profitability, Capital Efficiency, Growth, Financial Health, Cash Flow, Market Context, Dividend). Most cells for LULU should be non-`—`. PEG (5Y) row should show a value, **not** `—`. The Forward P/E trend chart should appear at the bottom with one line per peer across multiple periods.
4. **Step 4:** verify 8 sliders render with the new labels. Move the **Cash Quality** slider to 100% and all others to 0%. Verify the ranking reorders to put the peer with the highest free cash flow yield first. Move **Valuation Trend** to 100%. Verify ranking reorders again. Verify the AI recommendation references at least one of the new category names.

If any of the above fails, stop and fix the underlying bug — do NOT mark this task complete.

- [ ] **Step 6: Stop the Streamlit app and commit any cleanup**

```bash
# Stop streamlit (Ctrl-C in its terminal)
# If formatter/linter changes were made:
git add -A
git commit -m "chore: format and lint after scraper integration"
```

---

## Task 15: Final summary commit (optional)

**Files:**
- None (or `README.md` if it references metric counts)

- [ ] **Step 1: Check whether `README.md` mentions specific metric counts or categories**

Run: `grep -n "13 metrics\|6 categor\|yfinance" README.md`
Expected: lines that need updating. If found, update them to reference the new 22-field metric set, 8 scoring categories, and the Yahoo HTML scraper.

- [ ] **Step 2: Update `README.md` if needed**

Edit lines flagged in Step 1. Otherwise skip.

- [ ] **Step 3: Commit (only if changed)**

```bash
git add README.md
git commit -m "docs: update README for expanded metrics and 8 scoring categories"
```

---

## Self-review checklist

After completing all tasks:

- **Spec coverage:** Every section of [the design doc](../specs/2026-04-11-scrape-yahoo-key-statistics-design.md) is implemented:
  - Schema (Task 2) ✓
  - Converters (Task 3) ✓
  - Flat parsing (Task 5) ✓
  - Valuation table parsing (Task 6) ✓
  - Public fetch (Task 7) ✓
  - Stock service integration (Task 8) ✓
  - Scoring refactor + composites + derived (Tasks 9, 10) ✓
  - Step 3 grouped tables + trend chart (Task 11) ✓
  - Step 4 sliders (Task 12) ✓
  - Recommendation prompt (Task 13) ✓
  - Smoke (Task 14) ✓
- **Cache decorator:** The design specifies `@st.cache_data(ttl=10800)` on `fetch()`. **Open question for the implementer:** decide whether to add the decorator inside `yahoo_scraper.py` (simpler) or wrap `fetch` from `stock_service.py` (keeps the scraper free of Streamlit imports for non-UI use). The plan does **not** add the decorator because doing so couples the scraper to Streamlit; instead, the existing `state.METRICS_CACHE` in [step3_metrics.py](../../../app/ui/screens/step3_metrics.py) already memoizes per-session, which gives the same in-session benefit. If after the smoke test you observe Yahoo being hit on every Step 3 visit within a session, add `@st.cache_data(ttl=10800)` either at the top of `fetch` (and accept the streamlit import in the scraper) or as a wrapper in `stock_service.get_stock_metrics`.
