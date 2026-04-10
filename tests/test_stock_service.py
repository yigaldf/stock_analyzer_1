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
