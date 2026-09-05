"""Tests for GET /api/markets/movers."""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from app.api.main import app

pytestmark = pytest.mark.asyncio

_MOCK_MOVERS = [
    {
        "symbol": "NVDA",
        "name": "NVIDIA Corp",
        "price": 900.0,
        "change_pct": 1.11,
        "volume": 500_000,
        "market_cap": 2e12,
    }
]


async def test_markets_movers_defaults_to_usa_gainers():
    app.state.API_KEY = ""
    with patch(
        "app.api.main.get_market_movers_multi",
        new_callable=AsyncMock,
        return_value=_MOCK_MOVERS,
    ) as mocked:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/api/markets/movers")

    mocked.assert_awaited_once_with("usa", "gainers")
    assert r.status_code == 200
    data = r.json()
    assert data["market"] == "usa"
    assert data["category"] == "gainers"
    assert data["movers"][0]["symbol"] == "NVDA"


async def test_markets_movers_accepts_market_and_category_query_params():
    app.state.API_KEY = ""
    with patch(
        "app.api.main.get_market_movers_multi",
        new_callable=AsyncMock,
        return_value=_MOCK_MOVERS,
    ) as mocked:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get(
                "/api/markets/movers",
                params={"market": "crypto", "category": "most_active"},
            )

    mocked.assert_awaited_once_with("crypto", "most_active")
    assert r.status_code == 200
    assert r.json()["market"] == "crypto"
    assert r.json()["category"] == "most_active"


async def test_markets_movers_rejects_unknown_market():
    app.state.API_KEY = ""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/api/markets/movers", params={"market": "moon"})

    assert r.status_code == 400


async def test_markets_movers_rejects_unknown_category():
    app.state.API_KEY = ""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/api/markets/movers", params={"category": "bogus"})

    assert r.status_code == 400


async def test_markets_movers_503_when_service_returns_none():
    app.state.API_KEY = ""
    with patch(
        "app.api.main.get_market_movers_multi",
        new_callable=AsyncMock,
        return_value=None,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/api/markets/movers")

    assert r.status_code == 503
