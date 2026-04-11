from unittest.mock import MagicMock, patch

from app.services.stock_service import (
    get_stock_info,
    get_stock_metrics,
    validate_tickers,
)
from app.models.schemas import QuarterlyValuation, StockMetrics


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


@patch("app.services.stock_service.yf.Ticker")
def test_get_stock_info_valid_ticker(mock_ticker):
    mock_ticker.return_value.info = {
        "longName": "Lululemon Athletica Inc.",
        "sector": "Consumer Cyclical",
        "currentPrice": 342.10,
        "marketCap": 58000000000,
    }
    info = get_stock_info("LULU")
    assert info is not None
    assert info.ticker == "LULU"
    assert info.name == "Lululemon Athletica Inc."
    assert info.sector == "Consumer Cyclical"
    assert info.current_price == 342.10
    assert info.market_cap == 58000000000.0


@patch("app.services.stock_service.yf.Ticker")
def test_get_stock_info_invalid_ticker_returns_none(mock_ticker):
    mock_ticker.return_value.info = {}
    assert get_stock_info("BOGUS") is None


@patch("app.services.stock_service.yf.Ticker")
def test_get_stock_info_on_exception_returns_none(mock_ticker):
    mock_ticker.side_effect = RuntimeError("network error")
    assert get_stock_info("LULU") is None


@patch("app.services.stock_service.yahoo_scraper.fetch")
def test_get_stock_metrics_delegates_to_scraper(mock_fetch):
    mock_fetch.return_value = StockMetrics(
        ticker="LULU",
        forward_pe=13.0,
        peg_ratio=0.90,
        source="httpx",
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
    assert m.source == "httpx"
    assert len(m.valuation_history) == 2
    mock_fetch.assert_called_once_with("LULU")


@patch("app.services.stock_service.yahoo_scraper.fetch")
def test_get_stock_metrics_returns_none_when_scraper_fails(mock_fetch):
    mock_fetch.return_value = None
    assert get_stock_metrics("BOGUS") is None
    mock_fetch.assert_called_once_with("BOGUS")
