from unittest.mock import MagicMock, patch

from app.services.stock_service import (
    get_stock_info,
    get_stock_metrics,
    validate_tickers,
)
from app.models.schemas import QuarterlyValuation, StockMetrics


@patch("app.services.stock_service.yahoo_scraper.fetch", return_value=None)
@patch("app.services.stock_service.yf.Ticker")
def test_validate_tickers_drops_invalid(mock_ticker, _mock_fetch):
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
    # Scraper fallback also finds nothing for the bogus ticker (mocked None),
    # so it stays dropped.
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


@patch("app.services.stock_service.yahoo_scraper.fetch", return_value=None)
@patch("app.services.stock_service.yf.Ticker")
def test_get_stock_info_invalid_ticker_returns_none(mock_ticker, _mock_fetch):
    # Both yfinance (empty) and the scraper fallback (None) fail.
    mock_ticker.return_value.info = {}
    assert get_stock_info("BOGUS") is None


@patch("app.services.stock_service.yahoo_scraper.fetch", return_value=None)
@patch("app.services.stock_service.yf.Ticker")
def test_get_stock_info_on_exception_returns_none(mock_ticker, _mock_fetch):
    # yfinance raises and the scraper fallback also finds nothing.
    mock_ticker.side_effect = RuntimeError("network error")
    assert get_stock_info("LULU") is None


@patch("app.services.stock_service.yahoo_scraper.fetch")
@patch("app.services.stock_service.yf.Ticker")
def test_get_stock_info_falls_back_to_scraper_when_yfinance_blocked(
    mock_ticker, mock_fetch
):
    # On cloud IPs (e.g. Hugging Face) Yahoo blocks yfinance, returning an
    # empty info dict. get_stock_info must then fall back to the scraper.
    mock_ticker.return_value.info = {}
    mock_fetch.return_value = StockMetrics(
        ticker="LULU",
        name="Lululemon Athletica Inc.",
        market_cap=58_000_000_000.0,
        source="playwright",
    )
    info = get_stock_info("LULU")
    assert info is not None
    assert info.ticker == "LULU"
    assert info.name == "Lululemon Athletica Inc."
    assert info.market_cap == 58_000_000_000.0
    # The Key Statistics page carries no sector or live price, so the
    # fallback degrades those fields (documented trade-off).
    assert info.sector == "Unknown"
    assert info.current_price == 0.0
    mock_fetch.assert_called_once_with("LULU")


@patch("app.services.stock_service.yahoo_scraper.fetch")
@patch("app.services.stock_service.yf.Ticker")
def test_get_stock_info_name_defaults_to_ticker_when_scraper_name_missing(
    mock_ticker, mock_fetch
):
    mock_ticker.return_value.info = {}
    mock_fetch.return_value = StockMetrics(
        ticker="LULU", name=None, market_cap=58_000_000_000.0
    )
    info = get_stock_info("LULU")
    assert info is not None
    assert info.name == "LULU"


@patch("app.services.stock_service.yahoo_scraper.fetch")
@patch("app.services.stock_service.yf.Ticker")
def test_get_stock_info_does_not_call_scraper_when_yfinance_succeeds(
    mock_ticker, mock_fetch
):
    mock_ticker.return_value.info = {
        "longName": "Lululemon Athletica Inc.",
        "sector": "Consumer Cyclical",
        "currentPrice": 342.10,
        "marketCap": 58_000_000_000,
    }
    info = get_stock_info("LULU")
    assert info is not None
    assert info.sector == "Consumer Cyclical"
    mock_fetch.assert_not_called()


@patch("app.services.stock_service.yahoo_scraper.fetch")
@patch("app.services.stock_service.yf.Ticker")
def test_validate_tickers_falls_back_to_scraper(mock_ticker, mock_fetch):
    # yfinance recognizes nothing (blocked); the scraper validates the
    # real tickers and rejects the bogus one.
    def ticker_side_effect(t):
        mock = MagicMock()
        mock.info = {}
        return mock

    def fetch_side_effect(t):
        if t in ("LULU", "NKE"):
            return StockMetrics(ticker=t, market_cap=1_000_000_000.0)
        return None

    mock_ticker.side_effect = ticker_side_effect
    mock_fetch.side_effect = fetch_side_effect
    result = validate_tickers(["LULU", "BOGUS", "NKE"])
    assert "LULU" in result
    assert "NKE" in result
    assert "BOGUS" not in result


@patch("app.services.stock_service.metrics_cache.set")
@patch("app.services.stock_service.metrics_cache.get", return_value=None)
@patch("app.services.stock_service.yahoo_scraper.fetch")
def test_get_stock_metrics_delegates_to_scraper(mock_fetch, _cache_get, _cache_set):
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


@patch("app.services.stock_service.metrics_cache.set")
@patch("app.services.stock_service.metrics_cache.get", return_value=None)
@patch("app.services.stock_service.yahoo_scraper.fetch")
def test_get_stock_metrics_returns_none_when_scraper_fails(mock_fetch, _cache_get, _cache_set):
    mock_fetch.return_value = None
    assert get_stock_metrics("BOGUS") is None
    mock_fetch.assert_called_once_with("BOGUS")
