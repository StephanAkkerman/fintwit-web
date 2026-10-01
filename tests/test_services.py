from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pandas as pd
import pytest

import app.services.market_hours_service as market_hours_service
import app.services.options_service as options_service
from app.services.events_service import get_economic_events
from app.services.market_hours_service import get_stock_market_hours
from app.services.options_service import get_options_overview
from app.services.reddit_service import get_reddit_hot_posts, is_valid_subreddit_name

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_service_caches():
    reset_market_hours_cache = getattr(
        market_hours_service, "_reset_cache_for_tests", None
    )
    reset_options_cache = getattr(options_service, "_reset_cache_for_tests", None)

    if callable(reset_market_hours_cache):
        reset_market_hours_cache()
    if callable(reset_options_cache):
        reset_options_cache()
    yield
    if callable(reset_market_hours_cache):
        reset_market_hours_cache()
    if callable(reset_options_cache):
        reset_options_cache()


# ---------------------------------------------------------------------------
# Events – get_economic_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_economic_events_success_parses_rows():
    html_fragment = """
        <table>
            <tr><td id="theDay1712793600">Thu</td></tr>
            <tr id="eventRowId_1001">
                <td class="first left">14:30</td>
                <td class="left flagCur noWrap"><span title="United States"></span> USD</td>
                <td class="sentiment noWrap"><i class="grayFullBullishIcon"></i><i class="grayFullBullishIcon"></i><i class="grayFullBullishIcon"></i></td>
                <td class="left event">Nonfarm Payrolls</td>
                <td id="eventActual_1001">250K</td>
                <td id="eventForecast_1001">230K</td>
                <td id="eventPrevious_1001">210K</td>
            </tr>
        </table>
        """

    client = AsyncMock()
    client.post = AsyncMock(return_value=_httpx_response(200, {"data": html_fragment}))

    result = await get_economic_events(client, limit=10)

    assert result is not None
    assert len(result) == 1
    assert result[0]["id"] == "1001"
    assert result[0]["event"] == "Nonfarm Payrolls"
    assert result[0]["zone"] == "united states"
    assert result[0]["currency"] == "USD"
    assert result[0]["actual"] == "250K"
    assert result[0]["forecast"] == "230K"
    assert result[0]["previous"] == "210K"
    assert result[0]["impact_score"] == 3
    assert result[0]["impact_emoji"] == "🟥"


@pytest.mark.asyncio
async def test_get_economic_events_http_error_returns_none():
    client = AsyncMock()
    client.post = AsyncMock(return_value=_httpx_response(503, {}))

    result = await get_economic_events(client)

    assert result is None


# ---------------------------------------------------------------------------
# Options – get_options_overview
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_options_overview_aggregates_calls_and_puts():
    payload = {
        "data": {
            "tableDataCalls": {
                "tableData": {
                    "asOf": "Apr 12, 2026",
                    "rows": [
                        {
                            "expiryDate": "Apr 17, 2026",
                            "strike": 200,
                            "last": "1.2",
                            "pctChange": "+12.3",
                            "volume": 1500,
                            "openINT": "3200",
                            "url": "/market-activity/stocks/aapl/option-chain/call-put-options/sample-call",
                        }
                    ],
                }
            },
            "tableDataPuts": {
                "tableData": {
                    "asOf": "Apr 12, 2026",
                    "rows": [
                        {
                            "expiryDate": "Apr 17, 2026",
                            "strike": 180,
                            "last": "0.9",
                            "pctChange": "-3.2",
                            "volume": 900,
                            "openINT": "2500",
                            "url": "/market-activity/stocks/aapl/option-chain/call-put-options/sample-put",
                        }
                    ],
                }
            },
        }
    }

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload

    client = AsyncMock()
    client.get = AsyncMock(return_value=response)

    result = await get_options_overview(client, symbols=["AAPL"])

    assert result is not None
    assert result["totals"]["call_volume"] == 1500
    assert result["totals"]["put_volume"] == 900
    assert result["totals"]["put_call_ratio"] == pytest.approx(0.6)
    assert len(result["most_active_contracts"]) == 2
    assert result["most_active_contracts"][0]["contract_type"] == "CALL"


@pytest.mark.asyncio
async def test_get_options_overview_returns_none_when_all_symbols_fail():
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "data": None,
        "status": {"rCode": 400},
    }

    client = AsyncMock()
    client.get = AsyncMock(return_value=response)

    result = await get_options_overview(client, symbols=["INVALID"])
    assert result is None


@pytest.mark.asyncio
async def test_get_options_overview_handles_null_rows_when_market_closed():
    empty = {"tableData": {"asOf": None, "headers": None, "rows": None}}
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "data": {"tableDataCalls": empty, "tableDataPuts": empty},
        "status": {"rCode": 200},
    }

    client = AsyncMock()
    client.get = AsyncMock(return_value=response)

    result = await get_options_overview(client, symbols=["AAPL"])

    assert result is not None
    assert result["totals"]["total_volume"] == 0
    assert result["most_active_contracts"] == []


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
# Market Hours – get_stock_market_hours (offline via exchange_calendars)
# ---------------------------------------------------------------------------

# 2026-06-12 is a Friday (regular NYSE/NASDAQ session)
# 2026-06-14 is a Saturday (weekend)
# NYSE regular hours: 9:30 AM–4:00 PM ET = 13:30–20:00 UTC
# NYSE pre-market:    4:00–9:30 AM ET   = 08:00–13:30 UTC
# NYSE after-hours:   4:00–8:00 PM ET   = 20:00–00:00 UTC


@pytest.mark.asyncio
async def test_get_stock_market_hours_returns_five_exchanges():
    result = await get_stock_market_hours()
    assert result is not None
    assert len(result) == 5
    assert {r["exchange"] for r in result} == {"NYSE", "NASDAQ", "LSE", "JPX", "HKEX"}


@pytest.mark.asyncio
async def test_get_stock_market_hours_row_structure():
    result = await get_stock_market_hours()
    assert result is not None
    valid_sessions = {"Open", "Pre-market", "After-hours", "Closed"}
    for row in result:
        assert "exchange" in row
        assert "session" in row
        assert "is_open" in row
        assert "timezone" in row
        assert "next_open" in row
        assert "next_close" in row
        assert row["session"] in valid_sessions
        assert isinstance(row["is_open"], bool)


@pytest.mark.asyncio
async def test_get_stock_market_hours_nyse_regular_session():
    # 2026-06-12 15:00 UTC = 11:00 AM ET (regular session)
    mock_ts = pd.Timestamp("2026-06-12 15:00:00", tz="UTC")
    with patch.object(market_hours_service, "_now_utc", return_value=mock_ts):
        market_hours_service._reset_cache_for_tests()
        result = await get_stock_market_hours()

    assert result is not None
    nyse = next(r for r in result if r["exchange"] == "NYSE")
    assert nyse["session"] == "Open"
    assert nyse["is_open"] is True
    assert nyse["next_close"] is not None
    assert nyse["next_open"] is None


@pytest.mark.asyncio
async def test_get_stock_market_hours_nyse_pre_market():
    # 2026-06-12 10:00 UTC = 6:00 AM ET (pre-market window: 4:00–9:30 AM)
    mock_ts = pd.Timestamp("2026-06-12 10:00:00", tz="UTC")
    with patch.object(market_hours_service, "_now_utc", return_value=mock_ts):
        market_hours_service._reset_cache_for_tests()
        result = await get_stock_market_hours()

    assert result is not None
    nyse = next(r for r in result if r["exchange"] == "NYSE")
    assert nyse["session"] == "Pre-market"
    assert nyse["is_open"] is True
    assert nyse["next_open"] is not None
    assert nyse["next_close"] is None


@pytest.mark.asyncio
async def test_get_stock_market_hours_nyse_after_hours():
    # 2026-06-12 21:00 UTC = 5:00 PM ET (after-hours window: 4:00–8:00 PM)
    mock_ts = pd.Timestamp("2026-06-12 21:00:00", tz="UTC")
    with patch.object(market_hours_service, "_now_utc", return_value=mock_ts):
        market_hours_service._reset_cache_for_tests()
        result = await get_stock_market_hours()

    assert result is not None
    nyse = next(r for r in result if r["exchange"] == "NYSE")
    assert nyse["session"] == "After-hours"
    assert nyse["is_open"] is True
    assert nyse["next_open"] is not None
    assert nyse["next_close"] is None


@pytest.mark.asyncio
async def test_get_stock_market_hours_weekend_closure():
    # 2026-06-14 15:00 UTC = Saturday
    mock_ts = pd.Timestamp("2026-06-14 15:00:00", tz="UTC")
    with patch.object(market_hours_service, "_now_utc", return_value=mock_ts):
        market_hours_service._reset_cache_for_tests()
        result = await get_stock_market_hours()

    assert result is not None
    nyse = next(r for r in result if r["exchange"] == "NYSE")
    assert nyse["session"] == "Closed"
    assert nyse["is_open"] is False
    assert nyse["closure_reason"] == "weekend"
    assert nyse["next_open"] is not None


@pytest.mark.asyncio
async def test_get_stock_market_hours_caching():
    mock_ts = pd.Timestamp("2026-06-12 15:00:00", tz="UTC")
    call_count = 0
    original_build = market_hours_service._build_row

    def counting_build(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return original_build(*args, **kwargs)

    with patch.object(market_hours_service, "_now_utc", return_value=mock_ts):
        market_hours_service._reset_cache_for_tests()
        with patch.object(
            market_hours_service, "_build_row", side_effect=counting_build
        ):
            first = await get_stock_market_hours()
            second = await get_stock_market_hours()

    assert first is not None
    assert second is not None
    assert first == second
    # _build_row called 5 times (one per exchange) only on the first call
    assert call_count == 5


def test_process_submission_media_keeps_the_title_and_classifies_media():
    from app.services.reddit_service import process_submission_media

    assert process_submission_media({"is_self": True}) == ([], None)

    image = {"is_self": False, "url": "https://i.redd.it/abc.png"}
    assert process_submission_media(image) == (["https://i.redd.it/abc.png"], "image")

    gallery = {
        "is_self": False,
        "is_gallery": True,
        "url": "https://www.reddit.com/gallery/xyz",
        "media_metadata": {
            "a": {"s": {"u": "https://preview.redd.it/a.jpg?w=1&amp;s=x"}},
            "b": {"s": {}},
        },
    }
    assert process_submission_media(gallery) == (
        ["https://preview.redd.it/a.jpg?w=1&s=x"],
        "gallery",
    )

    preview = {"images": [{"source": {"url": "https://external-preview.redd.it/p"}}]}
    video = {"is_self": False, "url": "https://v.redd.it/vid", "preview": preview}
    assert process_submission_media(video) == (
        ["https://external-preview.redd.it/p"],
        "video",
    )

    link = {"is_self": False, "url": "https://news.example.com/a", "preview": preview}
    assert process_submission_media(link) == (
        ["https://external-preview.redd.it/p"],
        "link",
    )


@pytest.mark.asyncio
async def test_get_reddit_hot_posts_image_post_has_preview_not_title_prefix():
    payload = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "img1",
                        "subreddit": "wallstreetbets",
                        "title": "My loss porn",
                        "selftext": "",
                        "author": "user1",
                        "score": 5,
                        "num_comments": 1,
                        "created_utc": 1700000000,
                        "permalink": "/r/wallstreetbets/comments/img1/x/",
                        "url": "https://i.redd.it/loss.jpeg",
                        "is_self": False,
                        "link_flair_text": "Loss",
                        "upvote_ratio": 0.93,
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

    post = posts[0]
    assert post["title"] == "My loss porn"
    assert post["image_urls"] == ["https://i.redd.it/loss.jpeg"]
    assert post["media_type"] == "image"
    assert post["link_url"] is None
    assert post["flair"] == "Loss"
    assert post["upvote_ratio"] == 0.93
    assert post["over_18"] is False


def test_is_valid_subreddit_name():
    assert is_valid_subreddit_name("wallstreetbets")
    assert is_valid_subreddit_name("CryptoCurrency")
    assert not is_valid_subreddit_name("bad/sub")
    assert not is_valid_subreddit_name("ab")
