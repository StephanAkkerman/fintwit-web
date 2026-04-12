from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import app.services.coingecko as coingecko_service
import app.services.market_hours_service as market_hours_service
from app.services.coingecko import get_crypto_info
from app.services.market_hours_service import get_stock_market_hours
from app.services.nft_service import get_trending_nfts
from app.services.reddit_service import get_reddit_hot_posts, is_valid_subreddit_name
from app.services.yahoo import get_stock_info

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_coingecko_cache():
    coingecko_service._reset_cache_for_tests()
    market_hours_service._reset_cache_for_tests()
    yield
    coingecko_service._reset_cache_for_tests()
    market_hours_service._reset_cache_for_tests()


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
    with patch(
        "app.services.yahoo.aiohttp.ClientSession",
        _mock_session(_mock_response(200, YAHOO_RESPONSE)),
    ):
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
            "result": [
                {"meta": {"regularMarketPrice": 185.0, "regularMarketVolume": 1}}
            ]
        }
    }
    with patch(
        "app.services.yahoo.aiohttp.ClientSession",
        _mock_session(_mock_response(200, data)),
    ):
        result = await get_stock_info("AAPL")

    # previousClose defaults to price itself, so change_percent == 0
    assert result is not None
    assert result["change_percent"] == 0.0


@pytest.mark.asyncio
async def test_get_stock_info_missing_price_returns_none():
    data = {"chart": {"result": [{"meta": {"regularMarketPrice": None}}]}}
    with patch(
        "app.services.yahoo.aiohttp.ClientSession",
        _mock_session(_mock_response(200, data)),
    ):
        result = await get_stock_info("AAPL")
    assert result is None


@pytest.mark.asyncio
async def test_get_stock_info_empty_result_returns_none():
    data = {"chart": {"result": None}}
    with patch(
        "app.services.yahoo.aiohttp.ClientSession",
        _mock_session(_mock_response(200, data)),
    ):
        result = await get_stock_info("INVALID")
    assert result is None


@pytest.mark.asyncio
async def test_get_stock_info_http_error_returns_none():
    with patch(
        "app.services.yahoo.aiohttp.ClientSession",
        _mock_session(_mock_response(404, {})),
    ):
        result = await get_stock_info("AAPL")
    assert result is None


@pytest.mark.asyncio
async def test_get_stock_info_exception_returns_none():
    with patch(
        "app.services.yahoo.aiohttp.ClientSession",
        side_effect=Exception("Network error"),
    ):
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
    with (
        patch(
            "app.services.coingecko.aiohttp.ClientSession",
            _mock_session(_mock_response(200, data)),
        ),
        patch(
            "app.services.coingecko.get_stock_info", new=AsyncMock(return_value=None)
        ),
    ):
        result = await get_crypto_info("UNKNOWN")

    assert result is None


@pytest.mark.asyncio
async def test_get_crypto_info_search_http_error_uses_yahoo_fallback():
    yahoo_fallback = {
        "price": 45000.0,
        "change_percent": 1.0,
        "volume": 10_000_000.0,
        "website": "https://finance.yahoo.com/quote/BTC-USD",
    }
    with (
        patch(
            "app.services.coingecko.aiohttp.ClientSession",
            _mock_session(_mock_response(429, {})),
        ),
        patch(
            "app.services.coingecko.get_stock_info",
            new=AsyncMock(return_value=yahoo_fallback),
        ),
    ):
        result = await get_crypto_info("BTC")

    assert result == yahoo_fallback


@pytest.mark.asyncio
async def test_get_crypto_info_price_http_error_uses_yahoo_fallback():
    yahoo_fallback = {
        "price": 45000.0,
        "change_percent": 1.0,
        "volume": 10_000_000.0,
        "website": "https://finance.yahoo.com/quote/BTC-USD",
    }
    mock_cs = _mock_session(
        _mock_response(200, COINGECKO_SEARCH_RESPONSE),
        _mock_response(429, {}),
    )
    with (
        patch("app.services.coingecko.aiohttp.ClientSession", mock_cs),
        patch(
            "app.services.coingecko.get_stock_info",
            new=AsyncMock(return_value=yahoo_fallback),
        ),
    ):
        result = await get_crypto_info("BTC")

    assert result == yahoo_fallback


@pytest.mark.asyncio
async def test_get_crypto_info_exception_returns_none():
    with (
        patch(
            "app.services.coingecko.aiohttp.ClientSession",
            side_effect=Exception("Network error"),
        ),
        patch(
            "app.services.coingecko.get_stock_info", new=AsyncMock(return_value=None)
        ),
    ):
        result = await get_crypto_info("BTC")

    assert result is None


@pytest.mark.asyncio
async def test_get_crypto_info_uses_cache_on_second_call():
    mock_cs = _mock_session(
        _mock_response(200, COINGECKO_SEARCH_RESPONSE),
        _mock_response(200, COINGECKO_PRICE_RESPONSE),
    )

    with patch("app.services.coingecko.aiohttp.ClientSession", mock_cs):
        first = await get_crypto_info("BTC")
        second = await get_crypto_info("BTC")

    assert first == second
    # First call performs 2 requests (search + price), second call is cache hit.
    session_obj = mock_cs.return_value.__aenter__.return_value
    assert session_obj.get.call_count == 2


# ---------------------------------------------------------------------------
# Reddit – get_reddit_hot_posts
# ---------------------------------------------------------------------------


def _httpx_response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(status_code=status_code, json=payload)


@pytest.mark.asyncio
async def test_get_reddit_hot_posts_success():
    payload = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "abc123",
                        "subreddit": "wallstreetbets",
                        "title": "WSB post",
                        "selftext": "Check this [https://example.com](https://example.com)",
                        "author": "user1",
                        "score": 100,
                        "num_comments": 12,
                        "created_utc": 1700000000,
                        "permalink": "/r/wallstreetbets/comments/abc123/wsb_post/",
                        "is_self": True,
                        "stickied": False,
                    }
                }
            ]
        }
    }
    client = AsyncMock()
    client.get = AsyncMock(return_value=_httpx_response(200, payload))

    with patch(
        "app.services.reddit_service._fetch_with_asyncpraw",
        new=AsyncMock(return_value=None),
    ):
        posts = await get_reddit_hot_posts(client, limit=1)

    assert posts is not None
    assert len(posts) == 1
    assert posts[0]["id"] == "abc123"
    assert posts[0]["subreddit"] == "wallstreetbets"
    assert posts[0]["description"] == "Check this https://example.com"


@pytest.mark.asyncio
async def test_get_reddit_hot_posts_filters_stickied():
    payload = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "sticky",
                        "title": "Sticky",
                        "is_self": True,
                        "stickied": True,
                    }
                },
                {
                    "data": {
                        "id": "normal",
                        "title": "Normal",
                        "is_self": True,
                        "stickied": False,
                    }
                },
            ]
        }
    }
    client = AsyncMock()
    client.get = AsyncMock(return_value=_httpx_response(200, payload))

    with patch(
        "app.services.reddit_service._fetch_with_asyncpraw",
        new=AsyncMock(return_value=None),
    ):
        posts = await get_reddit_hot_posts(client)

    assert posts is not None
    assert len(posts) == 1
    assert posts[0]["id"] == "normal"


@pytest.mark.asyncio
async def test_get_reddit_hot_posts_http_error_returns_none():
    client = AsyncMock()
    client.get = AsyncMock(return_value=_httpx_response(503, {}))

    with patch(
        "app.services.reddit_service._fetch_with_asyncpraw",
        new=AsyncMock(return_value=None),
    ):
        posts = await get_reddit_hot_posts(client)

    assert posts is None


@pytest.mark.asyncio
async def test_get_reddit_hot_posts_invalid_subreddit_returns_none():
    client = AsyncMock()
    posts = await get_reddit_hot_posts(client, subreddit_name="bad/sub")
    assert posts is None


@pytest.mark.asyncio
async def test_get_reddit_hot_posts_prefers_asyncpraw_result():
    client = AsyncMock()
    client.get = AsyncMock()

    praw_posts = [
        {
            "id": "praw1",
            "subreddit": "wallstreetbets",
            "title": "From asyncpraw",
            "description": "Text",
            "author": "user",
            "score": 1,
            "num_comments": 0,
            "created_utc": 1700000000,
            "url": "https://reddit.com",
            "image_urls": [],
        }
    ]

    with patch(
        "app.services.reddit_service._fetch_with_asyncpraw",
        new=AsyncMock(return_value=praw_posts),
    ):
        posts = await get_reddit_hot_posts(client)

    assert posts == praw_posts
    client.get.assert_not_called()


@pytest.mark.asyncio
async def test_get_reddit_hot_posts_falls_back_to_httpx_when_asyncpraw_none():
    payload = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "fallback1",
                        "subreddit": "wallstreetbets",
                        "title": "From httpx",
                        "selftext": "Body",
                        "author": "user",
                        "score": 2,
                        "num_comments": 1,
                        "created_utc": 1700000001,
                        "permalink": "/r/wallstreetbets/comments/fallback1/",
                        "is_self": True,
                        "stickied": False,
                    }
                }
            ]
        }
    }
    client = AsyncMock()
    client.get = AsyncMock(return_value=_httpx_response(200, payload))

    with patch(
        "app.services.reddit_service._fetch_with_asyncpraw",
        new=AsyncMock(return_value=None),
    ):
        posts = await get_reddit_hot_posts(client)

    assert posts is not None
    assert posts[0]["id"] == "fallback1"


# ---------------------------------------------------------------------------
# NFTs – get_trending_nfts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_trending_nfts_success_parses_fields():
    payload = {
        "nfts": [
            {
                "id": "doodles-official",
                "name": "Doodles",
                "symbol": "DOODLES",
                "thumb": "https://example.com/doodles.png",
                "native_currency_symbol": "eth",
                "floor_price_in_native_currency": 1.2345,
                "floor_price_24h_percentage_change": -3.21,
            }
        ]
    }

    client = AsyncMock()
    client.get = AsyncMock(return_value=_httpx_response(200, payload))

    result = await get_trending_nfts(client, limit=5)

    assert result is not None
    assert len(result) == 1
    assert result[0]["id"] == "doodles-official"
    assert result[0]["name"] == "Doodles"
    assert result[0]["symbol"] == "DOODLES"
    assert result[0]["floor_price"] == pytest.approx(1.2345)
    assert result[0]["floor_currency"] == "ETH"
    assert result[0]["floor_change_24h"] == pytest.approx(-3.21)
    assert result[0]["website"] == "https://www.coingecko.com/en/nft/doodles-official"


@pytest.mark.asyncio
async def test_get_trending_nfts_http_error_returns_none():
    client = AsyncMock()
    client.get = AsyncMock(return_value=_httpx_response(503, {}))

    result = await get_trending_nfts(client)

    assert result is None


# ---------------------------------------------------------------------------
# Market Hours – get_stock_market_hours
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stock_market_hours_maps_sessions():
    payload = {
        "quoteResponse": {
            "result": [
                {
                    "symbol": "SPY",
                    "marketState": "PRE",
                    "regularMarketTime": 1712746800,
                    "exchangeTimezoneName": "America/New_York",
                    "fullExchangeName": "NYSE Arca",
                },
                {
                    "symbol": "QQQ",
                    "marketState": "POST",
                    "regularMarketTime": 1712746800,
                    "exchangeTimezoneName": "America/New_York",
                    "fullExchangeName": "NASDAQ",
                },
                {
                    "symbol": "^FTSE",
                    "marketState": "REGULAR",
                    "regularMarketTime": 1712746800,
                    "exchangeTimezoneName": "Europe/London",
                    "fullExchangeName": "FTSE",
                },
            ]
        }
    }

    client = AsyncMock()
    client.get = AsyncMock(return_value=_httpx_response(200, payload))

    result = await get_stock_market_hours(client)

    assert result is not None
    by_exchange = {row["exchange"]: row for row in result}
    assert by_exchange["NYSE"]["session"] == "Pre-market"
    assert by_exchange["NYSE"]["is_open"] is True
    assert by_exchange["NASDAQ"]["session"] == "After-hours"
    assert by_exchange["NASDAQ"]["is_open"] is True
    assert by_exchange["LSE"]["session"] == "Open"
    assert by_exchange["LSE"]["is_open"] is True
    assert by_exchange["JPX"]["session"] == "Unknown"
    assert by_exchange["HKEX"]["session"] == "Unknown"


@pytest.mark.asyncio
async def test_get_stock_market_hours_http_error_returns_none():
    client = AsyncMock()
    client.get = AsyncMock(return_value=_httpx_response(503, {}))

    result = await get_stock_market_hours(client)

    assert result is None


@pytest.mark.asyncio
async def test_get_stock_market_hours_uses_cache_for_subsequent_calls():
    payload = {
        "quoteResponse": {
            "result": [
                {
                    "symbol": "SPY",
                    "marketState": "REGULAR",
                    "regularMarketTime": 1712746800,
                    "exchangeTimezoneName": "America/New_York",
                    "fullExchangeName": "NYSE Arca",
                }
            ]
        }
    }

    client = AsyncMock()
    client.get = AsyncMock(return_value=_httpx_response(200, payload))

    first = await get_stock_market_hours(client)
    second = await get_stock_market_hours(client)

    assert first is not None
    assert second is not None
    assert client.get.call_count == 1


@pytest.mark.asyncio
async def test_get_stock_market_hours_uses_stale_cache_when_rate_limited():
    payload = {
        "quoteResponse": {
            "result": [
                {
                    "symbol": "SPY",
                    "marketState": "PRE",
                    "regularMarketTime": 1712746800,
                    "exchangeTimezoneName": "America/New_York",
                    "fullExchangeName": "NYSE Arca",
                }
            ]
        }
    }

    client = AsyncMock()
    client.get = AsyncMock(
        side_effect=[
            _httpx_response(200, payload),
            _httpx_response(429, {}),
        ]
    )

    with patch.object(market_hours_service, "_CACHE_TTL_SECONDS", 0):
        first = await get_stock_market_hours(client)
        second = await get_stock_market_hours(client)

    assert first is not None
    assert second is not None
    assert first == second
    assert client.get.call_count == 2


def test_is_valid_subreddit_name():
    assert is_valid_subreddit_name("wallstreetbets")
    assert is_valid_subreddit_name("CryptoCurrency")
    assert not is_valid_subreddit_name("bad/sub")
    assert not is_valid_subreddit_name("ab")
