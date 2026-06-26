"""Tests for GET /api/stocks/market-movers."""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from app.api.main import app

pytestmark = pytest.mark.asyncio

_MOCK_PAYLOAD = {
    "session_type": "pre-market",
    "gainers": [
        {
            "symbol": "NVDA", "name": "NVIDIA Corp", "price": 900.0,
            "extended_price": 910.0, "change_pct": 1.11,
            "volume": 500_000, "market_cap": 2e12,
        }
    ],
    "losers": [
        {
            "symbol": "TSLA", "name": "Tesla Inc", "price": 200.0,
            "extended_price": 196.0, "change_pct": -2.0,
            "volume": 300_000, "market_cap": 6e11,
        }
    ],
}


async def test_market_movers_endpoint_returns_snapshot():
    app.state.API_KEY = ""
    with patch(
        "app.api.main.get_market_movers",
        new_callable=AsyncMock,
        return_value=_MOCK_PAYLOAD,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/api/stocks/market-movers")

    assert r.status_code == 200
    data = r.json()
    assert data["session_type"] == "pre-market"
    assert len(data["gainers"]) == 1
    assert data["gainers"][0]["symbol"] == "NVDA"
    assert len(data["losers"]) == 1


async def test_market_movers_endpoint_503_when_none():
    app.state.API_KEY = ""
    with patch(
        "app.api.main.get_market_movers",
        new_callable=AsyncMock,
        return_value=None,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/api/stocks/market-movers")

    assert r.status_code == 503
