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
