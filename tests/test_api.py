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
    mock_repo.latest.assert_called_once_with(50)


@pytest.mark.asyncio
async def test_list_posts_custom_limit(async_client):
    with patch("app.api.main.REPO") as mock_repo:
        mock_repo.latest = AsyncMock(return_value=[])
        await async_client.get(
            "/api/posts?limit=10", headers={"X-API-Key": "test-api-key"}
        )
    mock_repo.latest.assert_called_once_with(10)


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
            "/api/posts?limit=201", headers={"X-API-Key": "test-api-key"}
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
    classifier.assert_awaited_once_with(["AAPL", "BTC"])


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
