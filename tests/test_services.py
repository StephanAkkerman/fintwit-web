import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.yahoo import get_stock_info
from app.services.coingecko import get_crypto_info


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status: int, json_data: dict) -> MagicMock:
    """Return a mock async context manager that behaves like an aiohttp response."""
    response = MagicMock()
    response.status = status
    response.json = AsyncMock(return_value=json_data)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _mock_session(*responses) -> MagicMock:
    """
    Return a mock aiohttp.ClientSession async context manager.

    Each positional argument is a response context manager returned in order
    by successive calls to ``session.get()``.
    """
    session = MagicMock()
    if len(responses) == 1:
        session.get = MagicMock(return_value=responses[0])
    else:
        resp_iter = iter(responses)
        session.get = MagicMock(side_effect=lambda *a, **kw: next(resp_iter))
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    mock_cs = MagicMock(return_value=session)
    return mock_cs


# ---------------------------------------------------------------------------
# Yahoo Finance – get_stock_info
# ---------------------------------------------------------------------------

YAHOO_RESPONSE = {
    "chart": {
        "result": [
            {
                "meta": {
                    "regularMarketPrice": 185.0,
                    "previousClose": 182.0,
                    "regularMarketVolume": 50_000_000,
                }
            }
        ]
    }
}


@pytest.mark.asyncio
async def test_get_stock_info_success():
    with patch("app.services.yahoo.aiohttp.ClientSession", _mock_session(_mock_response(200, YAHOO_RESPONSE))):
        result = await get_stock_info("AAPL")

    assert result is not None
    assert result["price"] == 185.0
    assert abs(result["change_percent"] - ((185.0 - 182.0) / 182.0 * 100)) < 0.01
    assert result["volume"] == 50_000_000 * 185.0
    assert "yahoo" in result["website"]
    assert "AAPL" in result["website"]


@pytest.mark.asyncio
async def test_get_stock_info_zero_change_when_no_previous_close():
    data = {
        "chart": {
            "result": [{"meta": {"regularMarketPrice": 185.0, "regularMarketVolume": 1}}]
        }
    }
    with patch("app.services.yahoo.aiohttp.ClientSession", _mock_session(_mock_response(200, data))):
        result = await get_stock_info("AAPL")

    # previousClose defaults to price itself, so change_percent == 0
    assert result is not None
    assert result["change_percent"] == 0.0


@pytest.mark.asyncio
async def test_get_stock_info_missing_price_returns_none():
    data = {"chart": {"result": [{"meta": {"regularMarketPrice": None}}]}}
    with patch("app.services.yahoo.aiohttp.ClientSession", _mock_session(_mock_response(200, data))):
        result = await get_stock_info("AAPL")
    assert result is None


@pytest.mark.asyncio
async def test_get_stock_info_empty_result_returns_none():
    data = {"chart": {"result": None}}
    with patch("app.services.yahoo.aiohttp.ClientSession", _mock_session(_mock_response(200, data))):
        result = await get_stock_info("INVALID")
    assert result is None


@pytest.mark.asyncio
async def test_get_stock_info_http_error_returns_none():
    with patch("app.services.yahoo.aiohttp.ClientSession", _mock_session(_mock_response(404, {}))):
        result = await get_stock_info("AAPL")
    assert result is None


@pytest.mark.asyncio
async def test_get_stock_info_exception_returns_none():
    with patch("app.services.yahoo.aiohttp.ClientSession", side_effect=Exception("Network error")):
        result = await get_stock_info("AAPL")
    assert result is None


# ---------------------------------------------------------------------------
# CoinGecko – get_crypto_info
# ---------------------------------------------------------------------------

COINGECKO_SEARCH_RESPONSE = {
    "coins": [{"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"}]
}

COINGECKO_PRICE_RESPONSE = {
    "bitcoin": {
        "usd": 45_000.0,
        "usd_24h_change": 3.2,
        "usd_24h_vol": 25_000_000_000.0,
    }
}


@pytest.mark.asyncio
async def test_get_crypto_info_success():
    mock_cs = _mock_session(
        _mock_response(200, COINGECKO_SEARCH_RESPONSE),
        _mock_response(200, COINGECKO_PRICE_RESPONSE),
    )
    with patch("app.services.coingecko.aiohttp.ClientSession", mock_cs):
        result = await get_crypto_info("BTC")

    assert result is not None
    assert result["price"] == 45_000.0
    assert result["change_percent"] == 3.2
    assert result["volume"] == 25_000_000_000.0
    assert "bitcoin" in result["website"]


@pytest.mark.asyncio
async def test_get_crypto_info_no_coins_returns_none():
    data = {"coins": []}
    with patch("app.services.coingecko.aiohttp.ClientSession", _mock_session(_mock_response(200, data))):
        result = await get_crypto_info("UNKNOWN")
    assert result is None


@pytest.mark.asyncio
async def test_get_crypto_info_search_http_error_returns_none():
    with patch("app.services.coingecko.aiohttp.ClientSession", _mock_session(_mock_response(429, {}))):
        result = await get_crypto_info("BTC")
    assert result is None


@pytest.mark.asyncio
async def test_get_crypto_info_price_http_error_returns_none():
    mock_cs = _mock_session(
        _mock_response(200, COINGECKO_SEARCH_RESPONSE),
        _mock_response(429, {}),
    )
    with patch("app.services.coingecko.aiohttp.ClientSession", mock_cs):
        result = await get_crypto_info("BTC")
    assert result is None


@pytest.mark.asyncio
async def test_get_crypto_info_exception_returns_none():
    with patch("app.services.coingecko.aiohttp.ClientSession", side_effect=Exception("Network error")):
        result = await get_crypto_info("BTC")
    assert result is None
