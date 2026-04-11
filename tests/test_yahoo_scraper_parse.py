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


def test_parse_document_extracts_profitability(lulu_html):
    m = _parse_document(lulu_html, "LULU")
    # Profit margin and operating margin are both expressed as decimals
    # (0.1422 means 14.22%). We don't pin exact values since the fixture
    # can be refreshed — just require the parser extracted *something*
    # numeric that survives the percent conversion.
    assert m.profit_margin is not None
    assert -1.0 < m.profit_margin < 1.0
    assert m.operating_margin is not None
    assert -1.0 < m.operating_margin < 1.0


def test_parse_document_extracts_management(lulu_html):
    m = _parse_document(lulu_html, "LULU")
    assert m.roe is not None
    assert m.roa is not None


def test_parse_document_extracts_income_statement(lulu_html):
    m = _parse_document(lulu_html, "LULU")
    assert m.revenue_growth_yoy is not None
    # Earnings growth may be negative for some tickers; just require non-None.
    assert m.earnings_growth_yoy is not None


def test_parse_document_extracts_balance_sheet(lulu_html):
    m = _parse_document(lulu_html, "LULU")
    assert m.debt_to_equity is not None
    assert m.current_ratio is not None
    assert m.total_cash is not None
    assert m.total_debt is not None
    # Raw dollar magnitudes should be in the billions for LULU.
    assert m.total_cash > 1e8
    assert m.total_debt > 1e8


def test_parse_document_extracts_cash_flow(lulu_html):
    m = _parse_document(lulu_html, "LULU")
    assert m.operating_cash_flow is not None
    assert m.levered_free_cash_flow is not None


def test_parse_document_extracts_beta(lulu_html):
    m = _parse_document(lulu_html, "LULU")
    assert m.beta is not None
    # Beta is typically between -2 and 5 for real companies.
    assert -2 < m.beta < 5


def test_parse_document_dividend_fields_parseable(lulu_html):
    # LULU currently pays no dividend, so these may be None. The test only
    # verifies the parser didn't crash and the attributes exist.
    m = _parse_document(lulu_html, "LULU")
    assert hasattr(m, "forward_dividend_yield")
    assert hasattr(m, "payout_ratio")


def test_parse_document_extracts_valuation_snapshot(lulu_html):
    m = _parse_document(lulu_html, "LULU")
    # Current-column valuation snapshot should populate the top-level
    # StockMetrics fields.
    assert m.market_cap is not None
    assert m.market_cap > 1e9  # LULU is a multi-billion-dollar company
    assert m.enterprise_value is not None
    assert m.trailing_pe is not None
    assert m.trailing_pe > 0
    assert m.forward_pe is not None
    assert m.forward_pe > 0
    # PEG was the headline reliability bug this scraper was built for.
    assert m.peg_ratio is not None
    assert m.peg_ratio > 0
    assert m.price_to_sales is not None
    assert m.price_to_book is not None
    assert m.ev_to_revenue is not None
    assert m.ev_to_ebitda is not None


def test_parse_document_populates_valuation_history(lulu_html):
    m = _parse_document(lulu_html, "LULU")
    assert isinstance(m.valuation_history, list)
    assert len(m.valuation_history) >= 2
    # First entry must be the "Current" snapshot.
    assert m.valuation_history[0].period == "Current"
    # Top-level forward_pe should equal valuation_history[0].forward_pe
    # (they're parsed from the same cell).
    assert m.forward_pe == m.valuation_history[0].forward_pe
    # At least one historical entry (period != "Current") should have a
    # non-None forward_pe — Yahoo shows ~5 historical quarters.
    historical = [q for q in m.valuation_history if q.period != "Current"]
    assert len(historical) >= 1
    assert any(q.forward_pe is not None for q in historical)


def test_parse_document_valuation_history_labels_are_strings(lulu_html):
    m = _parse_document(lulu_html, "LULU")
    for q in m.valuation_history:
        assert isinstance(q.period, str)
        assert q.period  # non-empty
