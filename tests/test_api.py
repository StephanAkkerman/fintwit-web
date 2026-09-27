from unittest.mock import AsyncMock, patch

import pytest

from app.api.main import app
from tests.conftest import SAMPLE_TWEETS

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_posts_unauthorized(async_client):
    # Test that the API key dependency works
    response = await async_client.get("/api/posts")
    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


@pytest.mark.asyncio
async def test_stream_unauthorized(async_client):
    response = await async_client.get("/api/stream")
    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


# ---------------------------------------------------------------------------
# GET /api/posts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_posts_authorized_returns_200(async_client):
    with patch("app.api.main.REPO") as mock_repo:
        mock_repo.latest = AsyncMock(return_value=SAMPLE_TWEETS)
        response = await async_client.get(
            "/api/posts", headers={"X-API-Key": "test-api-key"}
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_posts_returns_tweet_list(async_client):
    with patch("app.api.main.REPO") as mock_repo:
        mock_repo.latest = AsyncMock(return_value=SAMPLE_TWEETS)
        response = await async_client.get(
            "/api/posts", headers={"X-API-Key": "test-api-key"}
        )
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == len(SAMPLE_TWEETS)


@pytest.mark.asyncio
async def test_list_posts_default_limit(async_client):
    with patch("app.api.main.REPO") as mock_repo:
        mock_repo.latest = AsyncMock(return_value=[])
        await async_client.get("/api/posts", headers={"X-API-Key": "test-api-key"})
    mock_repo.latest.assert_called_once_with(200, before_id=None, options_only=False)


@pytest.mark.asyncio
async def test_list_posts_custom_limit(async_client):
    with patch("app.api.main.REPO") as mock_repo:
        mock_repo.latest = AsyncMock(return_value=[])
        await async_client.get(
            "/api/posts?limit=10", headers={"X-API-Key": "test-api-key"}
        )
    mock_repo.latest.assert_called_once_with(10, before_id=None, options_only=False)


@pytest.mark.asyncio
async def test_list_posts_before_id_pagination(async_client):
    with patch("app.api.main.REPO") as mock_repo:
        mock_repo.latest = AsyncMock(return_value=[])
        await async_client.get(
            "/api/posts?limit=25&before_id=123",
            headers={"X-API-Key": "test-api-key"},
        )
    mock_repo.latest.assert_called_once_with(25, before_id=123, options_only=False)


@pytest.mark.asyncio
async def test_list_posts_options_only_true(async_client):
    with patch("app.api.main.REPO") as mock_repo:
        mock_repo.latest = AsyncMock(return_value=[])
        await async_client.get(
            "/api/posts?options_only=true", headers={"X-API-Key": "test-api-key"}
        )
    mock_repo.latest.assert_called_once_with(200, before_id=None, options_only=True)


@pytest.mark.asyncio
async def test_list_posts_since_hours_forwards_to_repo(async_client):
    with patch("app.api.main.REPO") as mock_repo:
        mock_repo.latest = AsyncMock(return_value=[])
        await async_client.get(
            "/api/posts?since_hours=24", headers={"X-API-Key": "test-api-key"}
        )
    mock_repo.latest.assert_called_once_with(
        200,
        before_id=None,
        options_only=False,
        since_hours=24,
    )


@pytest.mark.asyncio
async def test_list_posts_limit_too_low_returns_422(async_client):
    with patch("app.api.main.REPO") as mock_repo:
        mock_repo.latest = AsyncMock(return_value=[])
        response = await async_client.get(
            "/api/posts?limit=0", headers={"X-API-Key": "test-api-key"}
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_posts_limit_too_high_returns_422(async_client):
    with patch("app.api.main.REPO") as mock_repo:
        mock_repo.latest = AsyncMock(return_value=[])
        response = await async_client.get(
            "/api/posts?limit=2001", headers={"X-API-Key": "test-api-key"}
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_posts_since_hours_too_high_returns_422(async_client):
    with patch("app.api.main.REPO") as mock_repo:
        mock_repo.latest = AsyncMock(return_value=[])
        response = await async_client.get(
            "/api/posts?since_hours=169", headers={"X-API-Key": "test-api-key"}
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_posts_tweet_has_expected_fields(async_client):
    with patch("app.api.main.REPO") as mock_repo:
        mock_repo.latest = AsyncMock(return_value=[SAMPLE_TWEETS[0]])
        response = await async_client.get(
            "/api/posts", headers={"X-API-Key": "test-api-key"}
        )
    tweet = response.json()[0]
    for field in ("id", "text", "user_name", "tickers", "assets"):
        assert field in tweet


@pytest.mark.asyncio
async def test_list_posts_returns_empty_list_when_no_tweets(async_client):
    with patch("app.api.main.REPO") as mock_repo:
        mock_repo.latest = AsyncMock(return_value=[])
        response = await async_client.get(
            "/api/posts", headers={"X-API-Key": "test-api-key"}
        )
    assert response.json() == []


@pytest.mark.asyncio
async def test_debug_tweet_extracts_tickers_and_hashtags_from_text(async_client):
    classifier = AsyncMock(return_value=[])

    with (
        patch("app.api.main.REPO") as mock_repo,
        patch("app.api.main.BROADCAST") as mock_broadcast,
        patch("app.api.main.AssetEnricher") as mock_enricher_cls,
    ):
        mock_repo.upsert_many = AsyncMock(return_value=1)
        mock_broadcast.publish = AsyncMock()
        mock_enricher = mock_enricher_cls.return_value
        mock_enricher.classify = classifier

        response = await async_client.post(
            "/api/debug/tweet",
            json={"text": "Bullish on $AAPL and #BTC", "tickers": [], "hashtags": []},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["tickers"] == ["AAPL"]
    assert data["hashtags"] == ["BTC"]
    classifier.assert_awaited_once_with(["AAPL"])


@pytest.mark.asyncio
async def test_debug_tweet_adds_options_intent_metadata(async_client):
    classifier = AsyncMock(return_value=[])

    with (
        patch("app.api.main.REPO") as mock_repo,
        patch("app.api.main.BROADCAST") as mock_broadcast,
        patch("app.api.main.AssetEnricher") as mock_enricher_cls,
    ):
        mock_repo.upsert_many = AsyncMock(return_value=1)
        mock_broadcast.publish = AsyncMock()
        mock_enricher = mock_enricher_cls.return_value
        mock_enricher.classify = classifier

        response = await async_client.post(
            "/api/debug/tweet",
            json={"text": "$TSLA AUG 390c up about 15%", "tickers": [], "hashtags": []},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["is_options_tweet"] is True
    assert data["options_context"] is not None
    assert data["options_context"]["classification"] == "OPTIONS"
    assert data["options_context"]["side"] == "CALL"


@pytest.mark.asyncio
async def test_stocktwits_returns_data(async_client):
    app.state.http_client = AsyncMock()

    with patch("app.api.main.get_stocktwits_data", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = [
            {
                "stock_id": 1,
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "price": "190.0 (+2.1% 📈)",
                "val": "100",
            }
        ]

        response = await async_client.get(
            "/api/stocktwits?keyword=ts", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 200
    assert response.json()[0]["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_stocktwits_returns_empty_list_when_service_unavailable(async_client):
    app.state.http_client = AsyncMock()

    with patch("app.api.main.get_stocktwits_data", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        response = await async_client.get(
            "/api/stocktwits?keyword=ts", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_options_overview_returns_data(async_client):
    app.state.http_client = AsyncMock()

    with patch("app.api.main.get_options_overview", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "totals": {
                "call_volume": 1000,
                "put_volume": 800,
                "total_volume": 1800,
                "put_call_ratio": 0.8,
            },
            "symbols": [],
            "bullish": [],
            "bearish": [],
            "most_active_contracts": [],
            "source": "nasdaq",
        }

        response = await async_client.get(
            "/api/options/overview", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 200
    assert response.json()["source"] == "nasdaq"
    mock_get.assert_awaited_once_with(app.state.http_client, None)


@pytest.mark.asyncio
async def test_options_overview_returns_503_when_service_unavailable(async_client):
    app.state.http_client = AsyncMock()

    with patch("app.api.main.get_options_overview", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        response = await async_client.get(
            "/api/options/overview", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Service Unavailable"}


@pytest.mark.asyncio
async def test_options_chain_returns_data(async_client):
    with patch("app.api.main.get_options_chain", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "symbol": "AAPL",
            "underlying": {"name": "Apple Inc.", "last_price": 152.3},
            "expirations": ["2026-09-19"],
            "expiration": "2026-09-19",
            "contracts": [],
            "source": "yfinance",
        }

        response = await async_client.get(
            "/api/options/chain?symbol=AAPL", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 200
    assert response.json()["symbol"] == "AAPL"
    mock_get.assert_awaited_once_with("AAPL", None)


@pytest.mark.asyncio
async def test_options_chain_returns_503_when_service_unavailable(async_client):
    with patch("app.api.main.get_options_chain", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        response = await async_client.get(
            "/api/options/chain?symbol=ZZZZ", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Service Unavailable"}


@pytest.mark.asyncio
async def test_news_company_returns_data(async_client):
    app.state.sentiment_model = None
    with patch("app.api.main.get_company_news", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = [
            {
                "symbols": ["AAPL"],
                "title": "AAPL rallies",
                "excerpt": "Some summary text.",
                "url": "https://example.com/a",
                "date": "2026-09-01T12:00:00Z",
                "source": "Reuters",
            }
        ]

        response = await async_client.get(
            "/api/news/company?symbols=AAPL", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "yfinance"
    assert len(body["articles"]) == 1
    # No model loaded: articles keep their shape, just unscored.
    assert body["articles"][0]["sentiment_label"] is None
    assert body["sentiment"]["analyzed"] == 0
    mock_get.assert_awaited_once_with(["AAPL"], 10)


@pytest.mark.asyncio
async def test_news_company_scores_articles_with_sentiment_model(async_client):
    model = AsyncMock()
    model.classify_parts.return_value = {
        "main": {"label": "BEARISH", "score": -0.9},
        "quoted": None,
        "tickers": {},
    }
    app.state.sentiment_model = model
    try:
        with patch("app.api.main.get_company_news", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [
                {
                    "symbols": ["AAPL"],
                    "title": "AAPL plunges on probe",
                    "excerpt": None,
                    "url": "https://example.com/api-bearish",
                    "date": "2026-09-01T12:00:00Z",
                    "source": "Reuters",
                }
            ]

            response = await async_client.get(
                "/api/news/company?symbols=AAPL",
                headers={"X-API-Key": "test-api-key"},
            )
    finally:
        app.state.sentiment_model = None

    assert response.status_code == 200
    body = response.json()
    assert body["articles"][0]["sentiment_label"] == "BEARISH"
    assert body["sentiment"]["bearish"] == 1
    assert body["sentiment"]["label"] == "BEARISH"


@pytest.mark.asyncio
async def test_news_company_returns_503_when_service_unavailable(async_client):
    with patch("app.api.main.get_company_news", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        response = await async_client.get(
            "/api/news/company?symbols=AAPL", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Service Unavailable"}


@pytest.mark.asyncio
async def test_economic_events_returns_data(async_client):
    app.state.http_client = AsyncMock()

    with patch("app.api.main.get_economic_events", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = [
            {
                "id": "1001",
                "date": "11/04/2024",
                "time": "14:30",
                "zone": "united states",
                "currency": "USD",
                "event": "Nonfarm Payrolls",
                "actual": "250K",
                "forecast": "230K",
                "previous": "210K",
                "impact_score": 3,
                "impact_emoji": "🟥",
                "source": "https://www.investing.com/economic-calendar/",
            }
        ]

        response = await async_client.get(
            "/api/events/economic?limit=10", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 200
    assert response.json()[0]["id"] == "1001"
    assert response.json()[0]["impact_emoji"] == "🟥"
    mock_get.assert_awaited_once_with(app.state.http_client, limit=10)


@pytest.mark.asyncio
async def test_economic_events_returns_503_when_service_unavailable(async_client):
    app.state.http_client = AsyncMock()

    with patch("app.api.main.get_economic_events", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        response = await async_client.get(
            "/api/events/economic", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Service Unavailable"}


@pytest.mark.asyncio
async def test_earnings_calendar_returns_data(async_client):
    app.state.http_client = AsyncMock()

    with patch(
        "app.api.main.get_earnings_calendar", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = {
            "start_date": "2026-09-03",
            "end_date": "2026-09-09",
            "days": [
                {
                    "date": "2026-09-03",
                    "count": 1,
                    "rows": [
                        {
                            "symbol": "AAPL",
                            "name": "Apple Inc.",
                            "date": "2026-09-03",
                            "session": "after-hours",
                            "session_emoji": "🌙",
                            "market_cap": 3_000_000_000_000.0,
                            "eps_forecast": 1.25,
                            "num_estimates": 12,
                            "fiscal_quarter_ending": "Sep/2026",
                            "last_year_eps": 1.10,
                            "last_year_report_date": "08/01/2025",
                            "website": "https://www.nasdaq.com/market-activity/stocks/aapl/earnings",
                        }
                    ],
                }
            ],
            "source": "nasdaq",
        }

        response = await async_client.get(
            "/api/earnings/calendar?days=3", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "nasdaq"
    assert body["days"][0]["rows"][0]["symbol"] == "AAPL"
    mock_get.assert_awaited_once_with(app.state.http_client, days=3, limit_per_day=10)


@pytest.mark.asyncio
async def test_earnings_calendar_returns_503_when_service_unavailable(async_client):
    app.state.http_client = AsyncMock()

    with patch(
        "app.api.main.get_earnings_calendar", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = None

        response = await async_client.get(
            "/api/earnings/calendar", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Service Unavailable"}


@pytest.mark.asyncio
async def test_earnings_calendar_rejects_invalid_days(async_client):
    response = await async_client.get(
        "/api/earnings/calendar?days=99", headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_stock_market_hours_returns_data(async_client):
    app.state.http_client = AsyncMock()

    with patch(
        "app.api.main.get_stock_market_hours", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = [
            {
                "exchange": "NYSE",
                "symbol": "SPY",
                "session": "Pre-market",
                "is_open": True,
                "market_state": "PRE",
                "as_of": "2026-04-10T11:00:00+00:00",
                "timezone": "America/New_York",
                "exchange_name": "NYSE Arca",
            }
        ]

        response = await async_client.get(
            "/api/stocks/market-hours", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 200
    assert response.json()[0]["exchange"] == "NYSE"
    mock_get.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_stock_market_hours_returns_503_when_service_unavailable(async_client):
    app.state.http_client = AsyncMock()

    with patch(
        "app.api.main.get_stock_market_hours", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = None

        response = await async_client.get(
            "/api/stocks/market-hours", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Service Unavailable"}


@pytest.mark.asyncio
async def test_reddit_wsb_returns_data(async_client):
    app.state.http_client = AsyncMock()

    with patch("app.api.main.get_reddit_hot_posts", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = [
            {
                "id": "abc123",
                "subreddit": "wallstreetbets",
                "title": "WSB post",
                "description": "Text",
                "author": "user1",
                "score": 10,
                "num_comments": 2,
                "created_utc": 1700000000,
                "url": "https://www.reddit.com/r/wallstreetbets/comments/abc123",
                "image_urls": [],
            }
        ]

        response = await async_client.get(
            "/api/reddit/wsb", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 200
    assert response.json()[0]["id"] == "abc123"


@pytest.mark.asyncio
async def test_reddit_wsb_invalid_subreddit_returns_400(async_client):
    response = await async_client.get(
        "/api/reddit/wsb?subreddit=bad/sub",
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid subreddit"}


@pytest.mark.asyncio
async def test_portfolio_create_position(async_client):
    with patch("app.api.main.PORTFOLIO_REPO") as mock_repo:
        mock_repo.create_position = AsyncMock(
            return_value={
                "id": 1,
                "broker": "IBKR",
                "symbol": "AAPL",
                "quantity": 10.0,
                "avg_cost": 150.0,
                "currency": "USD",
                "is_active": True,
            }
        )

        response = await async_client.post(
            "/api/portfolio/positions",
            headers={"X-API-Key": "test-api-key"},
            json={"symbol": "aapl", "quantity": 10, "avg_cost": 150},
        )

    assert response.status_code == 200
    assert response.json()["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_portfolio_list_positions(async_client):
    with patch("app.api.main.PORTFOLIO_REPO") as mock_repo:
        mock_repo.list_positions = AsyncMock(
            return_value=[{"id": 1, "symbol": "AAPL", "broker": "IBKR"}]
        )

        response = await async_client.get(
            "/api/portfolio/positions", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 200
    assert response.json()[0]["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_portfolio_delete_position_not_found(async_client):
    with patch("app.api.main.PORTFOLIO_REPO") as mock_repo:
        mock_repo.delete_position = AsyncMock(return_value=False)
        response = await async_client.delete(
            "/api/portfolio/positions/99", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Position not found"}


@pytest.mark.asyncio
async def test_portfolio_summary_returns_totals(async_client):
    with (
        patch("app.api.main.PORTFOLIO_REPO") as mock_repo,
        patch("app.api.main.get_stock_info", new_callable=AsyncMock) as mock_quote,
    ):
        mock_repo.list_positions = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "broker": "IBKR",
                    "symbol": "AAPL",
                    "quantity": 10.0,
                    "avg_cost": 100.0,
                    "currency": "USD",
                    "is_active": True,
                }
            ]
        )
        mock_quote.return_value = {
            "price": 120.0,
            "website": "https://finance.yahoo.com/quote/AAPL",
        }

        response = await async_client.get(
            "/api/portfolio/summary", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["totals"]["positions"] == 1
    assert data["totals"]["unrealized_pnl"] == 200.0


# ---------------------------------------------------------------------------
# Reddit trend integration (issue #6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reddit_trends_empty_before_the_first_run(async_client):
    with patch(
        "app.api.main.REDDIT_TREND_REPO.latest_run", new_callable=AsyncMock
    ) as m:
        m.return_value = None
        response = await async_client.get(
            "/api/reddit/trends", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 200
    body = response.json()
    # "Never scraped" must be distinguishable from "package not installed",
    # so the widget can say which.
    assert body["captured_at"] is None
    assert body["tickers"] == []
    assert body["subreddits"]


@pytest.mark.asyncio
async def test_reddit_trends_returns_the_stored_run(async_client):
    with patch(
        "app.api.main.REDDIT_TREND_REPO.latest_run", new_callable=AsyncMock
    ) as m:
        m.return_value = {
            "captured_at": "2026-09-15T00:00:00+00:00",
            "mood": "bullish",
            "subreddits": ["wallstreetbets"],
            "tickers": [{"symbol": "NVDA", "mentions": 41, "momentum": 1.21}],
        }
        response = await async_client.get(
            "/api/reddit/trends?limit=5", headers={"X-API-Key": "test-api-key"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["tickers"][0]["symbol"] == "NVDA"


@pytest.mark.asyncio
async def test_reddit_trend_history(async_client):
    with patch(
        "app.api.main.REDDIT_TREND_REPO.ticker_history", new_callable=AsyncMock
    ) as m:
        m.return_value = [{"mentions": 10}, {"mentions": 20}]
        response = await async_client.get(
            "/api/reddit/trends/nvda/history?days=7",
            headers={"X-API-Key": "test-api-key"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "NVDA"
    assert len(body["points"]) == 2


@pytest.mark.asyncio
async def test_reddit_categories(async_client):
    response = await async_client.get(
        "/api/reddit/categories", headers={"X-API-Key": "test-api-key"}
    )

    assert response.status_code == 200
    body = response.json()
    assert "default" in body
    assert isinstance(body["categories"], dict)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["ab", "way-too-punctuated!"])
async def test_reddit_summary_invalid_subreddit_returns_400(async_client, bad):
    # Guards the name before it reaches the scraper. A slash cannot be tested
    # here: it never matches the route in the first place.
    response = await async_client.get(
        f"/api/reddit/summary/{bad}", headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_reddit_summary_without_the_package_returns_503(async_client):
    from app.services import reddit_trends_service

    with patch.object(
        reddit_trends_service,
        "fetch_subreddit_summary",
        AsyncMock(side_effect=reddit_trends_service.RedditAnalyzerUnavailable("no")),
    ):
        response = await async_client.get(
            "/api/reddit/summary/wallstreetbets",
            headers={"X-API-Key": "test-api-key"},
        )

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_reddit_summary_returns_the_snapshot(async_client):
    from app.services import reddit_trends_service

    with patch.object(
        reddit_trends_service,
        "fetch_subreddit_summary",
        AsyncMock(
            return_value={
                "subreddit": "wallstreetbets",
                "sample_size": 40,
                "overall_mood": "bullish",
                "top_tickers": {"NVDA": 7},
                "posts": [],
            }
        ),
    ):
        response = await async_client.get(
            "/api/reddit/summary/wallstreetbets",
            headers={"X-API-Key": "test-api-key"},
        )

    assert response.status_code == 200
    assert response.json()["top_tickers"] == {"NVDA": 7}


# ---------------------------------------------------------------------------
# GET /api/x/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_x_status_reports_stream_state(async_client):
    state = {"state": "auth_failed", "source": "cookies", "detail": "HTTP 401"}
    with patch.dict("app.api.main.STREAM_STATUS", state):
        response = await async_client.get(
            "/api/x/status", headers={"X-API-Key": "test-api-key"}
        )
    assert response.status_code == 200
    assert response.json() == state
