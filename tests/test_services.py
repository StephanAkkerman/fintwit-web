from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import app.services.coingecko as coingecko_service
from app.services.coingecko import get_crypto_info
from app.services.reddit_service import get_reddit_hot_posts, is_valid_subreddit_name
from app.services.yahoo import get_stock_info

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_coingecko_cache():
    coingecko_service._reset_cache_for_tests()
    yield
    coingecko_service._reset_cache_for_tests()


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


def test_is_valid_subreddit_name():
    assert is_valid_subreddit_name("wallstreetbets")
    assert is_valid_subreddit_name("CryptoCurrency")
    assert not is_valid_subreddit_name("bad/sub")
    assert not is_valid_subreddit_name("ab")
