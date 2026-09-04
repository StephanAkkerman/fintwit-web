from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import app.services.options_chain_service as options_chain_service
from app.services.options_chain_service import get_options_chain


@pytest.fixture(autouse=True)
def _reset_cache():
    options_chain_service._reset_cache_for_tests()
    yield
    options_chain_service._reset_cache_for_tests()


def _underlying(**overrides):
    base = {
        "longName": "Apple Inc.",
        "regularMarketPrice": 152.3,
        "regularMarketChange": 1.2,
        "regularMarketChangePercent": 0.8,
        "marketCap": 2_500_000_000_000,
        "fiftyTwoWeekHigh": 199.6,
        "fiftyTwoWeekLow": 120.1,
        "regularMarketVolume": 50_000_000,
    }
    base.update(overrides)
    return base


def _contract_row(**overrides):
    base = {
        "strike": 150.0,
        "bid": 1.0,
        "ask": 1.2,
        "lastPrice": 1.1,
        "volume": 100,
        "openInterest": 500,
        "impliedVolatility": 0.35,
        "percentChange": 2.5,
        "inTheMoney": False,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_get_options_chain_returns_nearest_expiration_by_default():
    calls = pd.DataFrame([_contract_row()])
    puts = pd.DataFrame([_contract_row(inTheMoney=True)])
    ticker = MagicMock()
    ticker.options = ("2026-09-19", "2026-09-26")
    ticker.option_chain.return_value = (calls, puts, _underlying())

    with patch("yfinance.Ticker", return_value=ticker) as mock_ticker_cls:
        result = await get_options_chain("aapl")

    mock_ticker_cls.assert_called_once_with("AAPL")
    ticker.option_chain.assert_called_once_with(None)
    assert result["symbol"] == "AAPL"
    assert result["source"] == "yfinance"
    assert result["expiration"] == "2026-09-19"
    assert result["expirations"] == ["2026-09-19", "2026-09-26"]
    assert result["underlying"]["name"] == "Apple Inc."
    assert result["underlying"]["last_price"] == 152.3
    assert len(result["contracts"]) == 2
    assert {c["option_type"] for c in result["contracts"]} == {"CALL", "PUT"}


@pytest.mark.asyncio
async def test_get_options_chain_uses_requested_expiration():
    calls = pd.DataFrame([_contract_row(strike=160.0)])
    puts = pd.DataFrame([])
    ticker = MagicMock()
    ticker.options = ("2026-09-19", "2026-09-26")
    ticker.option_chain.return_value = (calls, puts, _underlying())

    with patch("yfinance.Ticker", return_value=ticker):
        result = await get_options_chain("AAPL", expiration="2026-09-26")

    ticker.option_chain.assert_called_once_with("2026-09-26")
    assert result["expiration"] == "2026-09-26"
    assert result["contracts"][0]["strike"] == 160.0


@pytest.mark.asyncio
async def test_get_options_chain_falls_back_to_nearest_on_invalid_expiration():
    calls = pd.DataFrame([_contract_row()])
    puts = pd.DataFrame([])
    ticker = MagicMock()
    ticker.options = ("2026-09-19",)
    ticker.option_chain.side_effect = [
        ValueError("bad date"),
        (calls, puts, _underlying()),
    ]

    with patch("yfinance.Ticker", return_value=ticker):
        result = await get_options_chain("AAPL", expiration="not-a-date")

    assert result["expiration"] == "2026-09-19"
    assert ticker.option_chain.call_count == 2


@pytest.mark.asyncio
async def test_get_options_chain_returns_none_when_no_options_market():
    ticker = MagicMock()
    ticker.option_chain.return_value = (None, None, None)
    ticker.options = ()

    with patch("yfinance.Ticker", return_value=ticker):
        result = await get_options_chain("ZZZZ")

    assert result is None


@pytest.mark.asyncio
async def test_get_options_chain_returns_none_on_fetch_error():
    with patch("yfinance.Ticker", side_effect=RuntimeError("network down")):
        result = await get_options_chain("AAPL")

    assert result is None


@pytest.mark.asyncio
async def test_get_options_chain_returns_none_for_blank_symbol():
    result = await get_options_chain("   ")

    assert result is None


@pytest.mark.asyncio
async def test_get_options_chain_caches_between_calls():
    calls = pd.DataFrame([_contract_row()])
    puts = pd.DataFrame([])
    ticker = MagicMock()
    ticker.options = ("2026-09-19",)
    ticker.option_chain.return_value = (calls, puts, _underlying())

    with patch("yfinance.Ticker", return_value=ticker) as mock_ticker_cls:
        await get_options_chain("AAPL")
        await get_options_chain("AAPL")

    mock_ticker_cls.assert_called_once()
