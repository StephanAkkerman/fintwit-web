"""Tests for GET /api/stocks/extended-hours."""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from app.api.main import app

pytestmark = pytest.mark.asyncio

_MOCK_PAYLOAD = {
    "session": "pre-market",
    "window_start": "2026-06-23T04:00:00-04:00",
    "window_end": "2026-06-23T09:30:00-04:00",
    "futures": [{"label": "ES", "symbol": "CME_MINI:ES1!", "price": 5800.0, "change_pct": 0.31}],
    "etfs": [{"symbol": "SPY", "price": 580.0, "extended_price": 581.5, "extended_change_pct": 0.26}],
    "tweet_stats": {
        "total_mentions": 42,
        "top_tickers": [{"ticker": "NVDA", "mentions": 10, "sentiment": "BULL"}],
        "sentiment_distribution": {"BULL": 20, "BEAR": 10, "NEUTRAL": 12},
    },
}


async def test_extended_hours_returns_snapshot():
    app.state.API_KEY = ""
    with patch(
        "app.api.main.get_extended_hours_snapshot",
        new_callable=AsyncMock,
        return_value=_MOCK_PAYLOAD,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/stocks/extended-hours")

    assert r.status_code == 200
    data = r.json()
    assert data["session"] == "pre-market"
    assert len(data["futures"]) == 1
    assert data["tweet_stats"]["total_mentions"] == 42


async def test_extended_hours_503_when_snapshot_none():
    app.state.API_KEY = ""
    with patch(
        "app.api.main.get_extended_hours_snapshot",
        new_callable=AsyncMock,
        return_value=None,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/stocks/extended-hours")

    assert r.status_code == 503
