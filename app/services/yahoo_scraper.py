"""Yahoo Finance Key Statistics scraper.

Public surface: `fetch(ticker)` returns a `StockMetrics` (possibly partial)
or `None` on hard failure.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx
from selectolax.parser import HTMLParser

from app.models.schemas import QuarterlyValuation, StockMetrics

logger = logging.getLogger(__name__)

_URL_TEMPLATE = "https://finance.yahoo.com/quote/{ticker}/key-statistics/?guccounter=1"
_HTTPX_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
_HTTPX_TIMEOUT = 10.0  # seconds
_PLAYWRIGHT_TIMEOUT_MS = 15_000  # milliseconds
_STUB_MIN_SIZE = 50_000  # bytes — below this we treat the response as an anti-bot stub

_client: httpx.Client | None = None


def _get_httpx_client() -> httpx.Client:
    """Lazily build and reuse one module-level httpx Client.

    Lazy creation lets pytest-httpx intercept calls without needing to
    monkeypatch a pre-instantiated client.
    """
    global _client
    if _client is None:
        _client = httpx.Client(
            timeout=_HTTPX_TIMEOUT, headers=_HTTPX_HEADERS, follow_redirects=True
        )
    return _client


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


# Label-to-field dispatch maps for the flat statistics sections on Yahoo's
# Key Statistics page. The exact label strings must match what the rendered
# page produces — Yahoo embeds double spaces before parenthetical qualifiers
# like "(ttm)"/"(mrq)"/"(yoy)" and appends bare footnote digits (e.g. the
# "4" in "Payout Ratio4") directly to the label text, with no separator.
_Converter = Callable[[str | None], float | None]


_PROFITABILITY_MAP: dict[str, tuple[str, _Converter]] = {
    "Profit Margin": ("profit_margin", _to_percent),
    "Operating Margin  (ttm)": ("operating_margin", _to_percent),
}

_MANAGEMENT_MAP: dict[str, tuple[str, _Converter]] = {
    "Return on Assets  (ttm)": ("roa", _to_percent),
    "Return on Equity  (ttm)": ("roe", _to_percent),
}

_INCOME_MAP: dict[str, tuple[str, _Converter]] = {
    "Quarterly Revenue Growth  (yoy)": ("revenue_growth_yoy", _to_percent),
    "Quarterly Earnings Growth  (yoy)": ("earnings_growth_yoy", _to_percent),
}

_BALANCE_SHEET_MAP: dict[str, tuple[str, _Converter]] = {
    "Total Cash  (mrq)": ("total_cash", _to_magnitude),
    "Total Debt  (mrq)": ("total_debt", _to_magnitude),
    "Total Debt/Equity  (mrq)": ("debt_to_equity", _to_percent),
    "Current Ratio  (mrq)": ("current_ratio", _to_float),
}

_CASHFLOW_MAP: dict[str, tuple[str, _Converter]] = {
    "Operating Cash Flow  (ttm)": ("operating_cash_flow", _to_magnitude),
    "Levered Free Cash Flow  (ttm)": ("levered_free_cash_flow", _to_magnitude),
}

_PRICE_HISTORY_MAP: dict[str, tuple[str, _Converter]] = {
    "Beta (5Y Monthly)": ("beta", _to_float),
}

_DIVIDEND_MAP: dict[str, tuple[str, _Converter]] = {
    # Yahoo appends footnote digits directly to dividend labels (no space).
    "Forward Annual Dividend Yield4": ("forward_dividend_yield", _to_percent),
    "Payout Ratio4": ("payout_ratio", _to_percent),
}

_ALL_FLAT_MAPS: list[dict[str, tuple[str, _Converter]]] = [
    _PROFITABILITY_MAP,
    _MANAGEMENT_MAP,
    _INCOME_MAP,
    _BALANCE_SHEET_MAP,
    _CASHFLOW_MAP,
    _PRICE_HISTORY_MAP,
    _DIVIDEND_MAP,
]


# Maps Yahoo valuation-grid row labels to (shared field name, converter).
# The StockMetrics snapshot field and QuarterlyValuation attribute happen
# to have the same name for every row, so we store a single name. Label
# strings must match the fixture verbatim — Yahoo does NOT suffix these
# rows with "(ttm)"/"(mrq)", unlike the flat-section labels.
_VALUATION_MAP: dict[str, tuple[str, _Converter]] = {
    "Market Cap": ("market_cap", _to_magnitude),
    "Enterprise Value": ("enterprise_value", _to_magnitude),
    "Trailing P/E": ("trailing_pe", _to_float),
    "Forward P/E": ("forward_pe", _to_float),
    "PEG Ratio (5yr expected)": ("peg_ratio", _to_float),
    "Price/Sales": ("price_to_sales", _to_float),
    "Price/Book": ("price_to_book", _to_float),
    "Enterprise Value/Revenue": ("ev_to_revenue", _to_float),
    "Enterprise Value/EBITDA": ("ev_to_ebitda", _to_float),
}


def _parse_stat_rows(doc: HTMLParser) -> dict[str, str]:
    """Walk the document and return {label: raw_value_string} for every
    recognizable 2-cell row.

    Yahoo's Key Statistics page renders each flat section as a
    ``<table class="table yf-vaowmx">`` whose body contains ``<tr>`` rows
    with exactly two ``<td>`` cells: a ``label`` cell and a ``value`` cell.
    We rely on that shape universally: any ``<tr>`` with two ``<td>``
    children is treated as a label/value pair. First occurrence wins so
    that the flat-table parser isn't polluted by duplicate labels that
    might appear in the Valuation Measures historical grid.
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
    """Route parsed label/value rows into StockMetrics field values via
    per-section dispatch dicts. Unrecognized labels are ignored."""
    out: dict[str, float | None] = {}
    for label_map in _ALL_FLAT_MAPS:
        for label, (field, converter) in label_map.items():
            if label in rows:
                out[field] = converter(rows[label])
    return out


def _parse_valuation_table(
    doc: HTMLParser,
) -> tuple[dict[str, float | None], list[QuarterlyValuation]]:
    """Parse Yahoo's Valuation Measures historical grid.

    Yahoo renders this section as a ``<table>`` whose ``<thead>`` has a
    single ``<tr>`` with 7 ``<th>`` cells — an empty corner cell followed
    by 6 period labels ("Current" + 5 historical quarter dates). The
    ``<tbody>`` has one ``<tr>`` per metric with 7 ``<td>`` cells: a
    label cell followed by 6 value cells aligned with the header columns.

    Returns:
        snapshot: dict of StockMetrics field name -> value parsed from
                  the "Current" column (used to populate the top-level
                  StockMetrics valuation fields).
        history:  one QuarterlyValuation per period column (including
                  "Current"), in the left-to-right order Yahoo renders.
    """
    # 1. Find the header row that defines the period column labels. The
    #    valuation grid is the only <thead><tr> on the page with >= 6 <th>
    #    cells, so this selector is safe.
    period_labels: list[str] = []
    for tr in doc.css("thead tr"):
        th_cells = tr.css("th")
        if len(th_cells) >= 6:
            # First <th> is the empty corner cell; the rest are period labels.
            labels = [c.text(strip=True) for c in th_cells]
            # Drop the leading empty cell.
            period_labels = [label for label in labels[1:] if label]
            if period_labels:
                break

    if not period_labels:
        return {}, []

    # 2. Build one QuarterlyValuation per period column.
    histories: list[QuarterlyValuation] = [
        QuarterlyValuation(period=p) for p in period_labels
    ]

    # 3. Walk valuation rows and populate both snapshot + histories.
    #    A valuation row has 1 label <td> + N value <td>s where
    #    N == len(period_labels). Any row whose label isn't a known
    #    valuation metric is ignored.
    snapshot: dict[str, float | None] = {}
    expected_len = 1 + len(period_labels)
    for tr in doc.css("tr"):
        cells = tr.css("td")
        if len(cells) != expected_len:
            continue
        label = cells[0].text(strip=True)
        if label not in _VALUATION_MAP:
            continue
        field, converter = _VALUATION_MAP[label]
        for idx, value_cell in enumerate(cells[1:]):
            parsed = converter(value_cell.text(strip=True))
            setattr(histories[idx], field, parsed)
            if idx == 0:
                snapshot[field] = parsed

    return snapshot, histories


def _parse_company_name(doc: HTMLParser, ticker: str) -> str | None:
    """Extract the company display name from the page ``<title>``.

    Yahoo's Key Statistics ``<title>`` is shaped like
    ``"Lululemon Athletica Inc. (LULU) Valuation Measures ..."``. We take
    everything before the first ``" ("`` (the ticker parenthetical) and
    return it stripped. Returns None if the title is missing or doesn't
    contain a parenthetical (so callers can fall back to the bare ticker).
    """
    title_node = doc.css_first("title")
    if title_node is None:
        return None
    title = title_node.text(strip=True)
    if not title:
        return None
    name = title.split(" (", 1)[0].strip()
    return name or None


def _parse_document(html: str, ticker: str) -> StockMetrics | None:
    """Parse a Yahoo Key Statistics HTML page into a StockMetrics.

    Returns None on hard parse failure (root element missing). Otherwise
    returns a (possibly partial) StockMetrics populated from the flat
    statistics sections (Profitability, Management Effectiveness, Income
    Statement, Balance Sheet, Cash Flow, Stock Price History, and
    Dividends & Splits) plus the Valuation Measures historical grid
    (top-level snapshot fields + ``valuation_history``).
    """
    try:
        doc = HTMLParser(html)
    except Exception:
        return None
    if doc.body is None:
        return None

    rows = _parse_stat_rows(doc)
    flat_fields = _apply_flat_maps(rows)

    snapshot, history = _parse_valuation_table(doc)
    # Valuation-grid snapshot is authoritative for valuation fields
    # (market_cap, forward_pe, peg_ratio, etc.) because it reads the
    # "Current" column of the historical grid. Flat-map fields cover the
    # disjoint non-valuation sections. On any future overlap, prefer the
    # valuation-grid value.
    merged = {**flat_fields, **snapshot}

    return StockMetrics(
        ticker=ticker,
        name=_parse_company_name(doc, ticker),
        valuation_history=history,
        **merged,
    )


def _looks_like_anti_bot_stub(html: str, ticker: str | None = None) -> bool:
    """Detect Yahoo's anti-bot 404 stub.

    Yahoo serves a ~500-byte JS redirect page with the phrase
    'Content is currently unavailable' when its edge layer rejects a
    bare HTTP client. Real rendered pages are north of 200 KB.

    Returns True on either signal. The two conditions are logged
    separately so ops can tell the phrase-based and size-based matches
    apart (a size-only match on a real ticker would be suspicious).
    """
    if "Content is currently unavailable" in html:
        return True
    if len(html) < _STUB_MIN_SIZE:
        logger.warning(
            "yahoo_scraper: httpx response for %s is %d bytes (< %d) "
            "with no stub phrase; treating as stub",
            ticker or "<unknown>",
            len(html),
            _STUB_MIN_SIZE,
        )
        return True
    return False


def _fetch_via_httpx(ticker: str) -> str | None:
    """Try the fast httpx path. Returns HTML on success, None on any failure.

    'Failure' includes HTTP errors, non-200 status, or an anti-bot stub.
    """
    url = _URL_TEMPLATE.format(ticker=ticker)
    try:
        response = _get_httpx_client().get(url)
    except httpx.HTTPError as exc:
        logger.warning("yahoo_scraper: httpx error for %s: %s", ticker, exc)
        return None
    if response.status_code != 200:
        logger.warning(
            "yahoo_scraper: httpx non-200 (%s) for %s",
            response.status_code,
            ticker,
        )
        return None
    html = response.text
    if _looks_like_anti_bot_stub(html, ticker=ticker):
        logger.info(
            "yahoo_scraper: httpx returned anti-bot stub for %s, "
            "will fall back to playwright",
            ticker,
        )
        return None
    return html


def _fetch_via_playwright(ticker: str) -> str | None:
    """Fallback path: render the page in a real Chromium browser.

    Handles Yahoo's full GDPR consent flow for fresh contexts:

      1. Navigate to the key-statistics URL. Yahoo will typically
         redirect to ``consent.yahoo.com/v2/collectConsent``.
      2. On the consent page, click the language-independent
         ``button[name="agree"]`` (label varies by locale — Hebrew,
         English, German, etc. — but the name attribute is stable).
      3. Yahoo then forwards to ``guce.yahoo.com/copyConsent``, which
         is a JavaScript refresh page with a hidden ``#doneUrl`` input.
         In headless Chromium the embedded cookie-copy XHRs don't
         reliably auto-forward, so we read the ``doneUrl`` and
         navigate there directly — the cookies set by the consent
         redirect chain come with us via the shared context.
      4. Wait for the stable ``[data-testid="qsp-statistics"]``
         anchor on the Valuation Measures section to confirm the page
         mounted, then dump ``page.content()``.

    If step 4's wait times out, we still return ``page.content()`` so
    the parser can salvage partial HTML; ``fetch()``'s signal-field
    guard decides whether the result is usable.

    The Chromium binary must be installed once via
    ``uv run playwright install chromium``. If Playwright or the
    binary is unavailable, returns None and logs a warning.
    """
    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except ImportError:
        logger.error(
            "yahoo_scraper: playwright package not installed; cannot fall back for %s",
            ticker,
        )
        return None

    url = _URL_TEMPLATE.format(ticker=ticker)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent=_HTTPX_HEADERS["User-Agent"],
                    locale="en-US",
                    viewport={"width": 1280, "height": 900},
                )
                page = context.new_page()
                page.goto(
                    url,
                    timeout=_PLAYWRIGHT_TIMEOUT_MS,
                    wait_until="domcontentloaded",
                )

                # Step 2: navigate the consent flow if Yahoo gated us.
                if "consent.yahoo.com" in page.url:
                    logger.info(
                        "yahoo_scraper: %s on consent page, clicking agree",
                        ticker,
                    )
                    try:
                        with page.expect_navigation(
                            wait_until="domcontentloaded",
                            timeout=_PLAYWRIGHT_TIMEOUT_MS,
                        ):
                            page.click('button[name="agree"]')
                    except PlaywrightError as exc:
                        logger.warning(
                            "yahoo_scraper: consent-agree click failed for %s: %s",
                            ticker,
                            exc,
                        )
                        return None

                # Step 3: the copyConsent forwarding page doesn't
                # reliably auto-redirect in headless mode — read its
                # doneUrl and navigate directly.
                if "copyConsent" in page.url:
                    try:
                        done_url = page.input_value("input#doneUrl", timeout=5_000)
                    except PlaywrightError as exc:
                        logger.warning(
                            "yahoo_scraper: could not read doneUrl on copyConsent "
                            "for %s: %s",
                            ticker,
                            exc,
                        )
                        return None
                    if not done_url:
                        logger.warning(
                            "yahoo_scraper: copyConsent doneUrl was empty for %s",
                            ticker,
                        )
                        return None
                    page.goto(
                        done_url,
                        timeout=_PLAYWRIGHT_TIMEOUT_MS,
                        wait_until="domcontentloaded",
                    )

                # Step 4: wait for the valuation measures section to mount.
                # The data-testid is stable across locales; text selectors
                # are not.
                try:
                    page.wait_for_selector(
                        '[data-testid="qsp-statistics"]',
                        timeout=_PLAYWRIGHT_TIMEOUT_MS,
                    )
                except PlaywrightError as exc:
                    # Don't bail — dump whatever rendered and let the
                    # parser decide. fetch()'s _metrics_has_any_data
                    # guard will treat zero-signal-field results as a
                    # parse failure and fall back appropriately.
                    logger.warning(
                        "yahoo_scraper: qsp-statistics selector timed out "
                        "for %s (%s); returning partial page content",
                        ticker,
                        exc,
                    )
                html = page.content()
            finally:
                context.close()
                browser.close()
        return html
    except PlaywrightError as exc:
        logger.warning("yahoo_scraper: playwright error for %s: %s", ticker, exc)
        return None
    except Exception as exc:  # unexpected (e.g. missing chromium binary)
        logger.warning(
            "yahoo_scraper: playwright unexpected error for %s: %s", ticker, exc
        )
        return None


_SIGNAL_FIELDS = (
    "forward_pe",
    "peg_ratio",
    "market_cap",
    "profit_margin",
    "operating_margin",
    "roe",
    "total_cash",
    "beta",
)
_MIN_SIGNAL_COUNT = 3


def _metrics_has_any_data(m: StockMetrics) -> bool:
    """Return True if parsed metrics contain enough non-None signal fields.

    A single field (e.g. forward_pe) can slip through from a partially-
    rendered anti-bot page. Require at least _MIN_SIGNAL_COUNT fields so
    that near-empty parses fall back to Playwright."""
    count = sum(1 for f in _SIGNAL_FIELDS if getattr(m, f) is not None)
    return count >= _MIN_SIGNAL_COUNT or bool(m.valuation_history)


def fetch(ticker: str) -> StockMetrics | None:
    """Fetch and parse Yahoo Key Statistics for one ticker.

    Tiered strategy:
      1. Try httpx (fast path). On parseable response, tag source='httpx'.
      2. If httpx fails OR the parsed result has zero signal fields, fall
         back to Playwright (real Chromium) and tag source='playwright'.
      3. If both backends produce empty/unparseable HTML, return None so
         the UI shows "Couldn't fetch metrics for X".

    Caching is intentionally left to the UI layer (Streamlit session
    cache) to keep this module framework-agnostic.
    """

    def _try_parse(html: str, source_label: str) -> StockMetrics | None:
        try:
            metrics = _parse_document(html, ticker)
        except Exception as exc:
            logger.warning(
                "yahoo_scraper: parse failed for %s via %s: %s",
                ticker,
                source_label,
                exc,
            )
            return None
        if metrics is None:
            return None
        if not _metrics_has_any_data(metrics):
            logger.warning(
                "yahoo_scraper: %s returned parseable HTML for %s but no "
                "signal fields extracted; treating as parse failure",
                source_label,
                ticker,
            )
            return None
        metrics.source = source_label  # type: ignore[assignment]
        return metrics

    # Primary: httpx
    html = _fetch_via_httpx(ticker)
    if html is not None:
        metrics = _try_parse(html, "httpx")
        if metrics is not None:
            return metrics

    # Fallback: Playwright
    html = _fetch_via_playwright(ticker)
    if html is None:
        return None
    return _try_parse(html, "playwright")
