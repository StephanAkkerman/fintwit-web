import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
def client():
    with patch("app.api.main.run_stream", new_callable=AsyncMock):
        from app.api.main import app

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def test_leaderboard_returns_list(client):
    resp = client.get("/api/traders/leaderboard")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_leaderboard_rejects_unsupported_horizon(client):
    resp = client.get("/api/traders/leaderboard?horizon_days=3")
    assert resp.status_code == 422


def test_leaderboard_accepts_supported_horizons(client):
    for horizon in (1, 7, 30):
        resp = client.get(f"/api/traders/leaderboard?horizon_days={horizon}")
        assert resp.status_code == 200


def test_trader_detail_returns_shape_for_unknown_user(client):
    resp = client.get("/api/traders/user/nobody-has-this-handle")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_screen_name"] == "nobody-has-this-handle"
    assert len(body["horizons"]) == 3
    assert body["recent_calls"] == []


class _FakeSentimentModel:
    def __init__(self, label: str, score: float):
        self._label = label
        self._score = score

    async def classify_parts(self, text: str):
        return {
            "main": {"label": self._label, "emoji": "🐂", "score": self._score},
            "quoted": None,
        }


@pytest.mark.asyncio
async def test_debug_tweet_records_a_pending_call_end_to_end():
    """A bullish debug-injected tweet mentioning a priced ticker should show
    up as a pending (ungraded) call on that author's trader detail page,
    exercising extract_calls -> TraderCallRepo -> the traders API read path
    against an isolated in-memory database."""
    from httpx import ASGITransport, AsyncClient

    from app.api.main import app
    import app.api.main as main_module
    from app.infra.db import Base
    from app.infra.repos import TraderCallRepo

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    test_session = async_sessionmaker(engine, expire_on_commit=False)
    test_repo = TraderCallRepo(test_session)

    app.state.sentiment_model = _FakeSentimentModel("BULLISH", 0.8)

    with (
        patch.object(main_module, "Session", test_session),
        patch.object(main_module, "TRADER_CALL_REPO", test_repo),
        patch.object(main_module, "REPO") as mock_repo,
        patch.object(main_module, "BROADCAST") as mock_broadcast,
        patch.object(main_module, "AssetEnricher") as mock_enricher_cls,
    ):
        mock_repo.upsert_many = AsyncMock(return_value=1)
        mock_broadcast.publish = AsyncMock()
        mock_enricher = mock_enricher_cls.return_value
        mock_enricher.classify = AsyncMock(
            return_value=[
                {
                    "symbol": "AAPL",
                    "kind": "EQUITY",
                    "financials": {"price": 200.0},
                }
            ]
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            post_resp = await ac.post(
                "/api/debug/tweet",
                json={
                    "text": "Loading up on $AAPL here",
                    "tickers": [],
                    "hashtags": [],
                    "user_screen_name": "call-tester",
                },
            )
            assert post_resp.status_code == 200

            detail_resp = await ac.get("/api/traders/user/call-tester")

    await engine.dispose()

    assert detail_resp.status_code == 200
    body = detail_resp.json()
    assert len(body["recent_calls"]) == 1
    call = body["recent_calls"][0]
    assert call["ticker"] == "AAPL"
    assert call["direction"] == "bullish"
    assert call["price_at_call"] == 200.0
    assert call["results"] == []  # not graded yet
