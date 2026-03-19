import pytest
from unittest.mock import AsyncMock, patch

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
