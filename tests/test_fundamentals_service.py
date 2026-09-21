from unittest.mock import MagicMock, patch

import pytest

import app.services.fundamentals_service as fundamentals_service
from app.services.fundamentals_service import get_fundamentals


@pytest.fixture(autouse=True)
def _reset_cache():
    fundamentals_service._reset_cache_for_tests()
    yield
    fundamentals_service._reset_cache_for_tests()


def _info(**overrides):
    base = {
        "marketCap": 3_000_000_000_000,
        "forwardPE": 30.7,
        "trailingPE": 41.1,
        "epsForward": 6.5,
        "epsTrailingTwelveMonths": 4.5,
        "averageDailyVolume3Month": 54_321_000,
        "averageDailyVolume10Day": 48_000_000,
        "currency": "usd",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_get_fundamentals_maps_yahoo_quote_fields():
    ticker = MagicMock()
    ticker.info = _info()

    with patch("yfinance.Ticker", return_value=ticker) as mock_ticker_cls:
        result = await get_fundamentals("aapl")

    mock_ticker_cls.assert_called_once_with("AAPL")
    assert result == {
        "market_cap": 3_000_000_000_000,
        "forward_pe": 30.7,
        "trailing_pe": 41.1,
        "eps_forward": 6.5,
        "eps_trailing": 4.5,
        "avg_volume": 54_321_000,
        "avg_volume_10d": 48_000_000,
        "currency": "USD",
    }


@pytest.mark.asyncio
async def test_get_fundamentals_includes_nav_for_etfs():
    ticker = MagicMock()
    ticker.info = _info(navPrice=101.23)

    with patch("yfinance.Ticker", return_value=ticker):
        result = await get_fundamentals("SPY")

    assert result["nav"] == 101.23


@pytest.mark.asyncio
async def test_get_fundamentals_omits_fields_yahoo_does_not_report():
    ticker = MagicMock()
    ticker.info = {"marketCap": 500_000_000, "currency": "USD"}

    with patch("yfinance.Ticker", return_value=ticker):
        result = await get_fundamentals("XYZ")

    assert result == {"market_cap": 500_000_000, "currency": "USD"}
    assert "forward_pe" not in result
    assert "nav" not in result


@pytest.mark.asyncio
async def test_get_fundamentals_returns_none_for_empty_info():
    ticker = MagicMock()
    ticker.info = {}

    with patch("yfinance.Ticker", return_value=ticker):
        result = await get_fundamentals("ZZZZ")

    assert result is None


@pytest.mark.asyncio
async def test_get_fundamentals_returns_none_when_only_currency_reported():
    ticker = MagicMock()
    ticker.info = {"currency": "USD"}

    with patch("yfinance.Ticker", return_value=ticker):
        result = await get_fundamentals("ZZZZ")

    assert result is None


@pytest.mark.asyncio
async def test_get_fundamentals_returns_none_on_fetch_failure():
    with patch("yfinance.Ticker", side_effect=RuntimeError("boom")):
        result = await get_fundamentals("AAPL")

    assert result is None


@pytest.mark.asyncio
async def test_get_fundamentals_returns_none_for_blank_symbol():
    result = await get_fundamentals("   ")
    assert result is None


@pytest.mark.asyncio
async def test_get_fundamentals_caches_per_symbol():
    ticker = MagicMock()
    ticker.info = _info()

    with patch("yfinance.Ticker", return_value=ticker) as mock_ticker_cls:
        await get_fundamentals("AAPL")
        await get_fundamentals("AAPL")

    mock_ticker_cls.assert_called_once()
