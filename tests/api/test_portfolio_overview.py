"""Tests for GET /api/portfolio/history and GET /api/portfolio/insights."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import main
from app.api.main import app

pytestmark = pytest.mark.asyncio

_HOLDINGS = [
    {
        "symbol": "AAPL",
        "quantity": 10,
        "avg_cost": 100.0,
        "cost_basis": 1000.0,
        "currency": "USD",
    }
]

_VALUATION = {
    "totals": {
        "positions": 1,
        "market_value": 1200.0,
        "cost_basis": 1000.0,
        "unrealized_pnl": 200.0,
        "unrealized_pnl_percent": 20.0,
    },
    "positions": [
        {
            **_HOLDINGS[0],
            "market_price": 120.0,
            "market_value": 1200.0,
            "unrealized_pnl": 200.0,
            "unrealized_pnl_percent": 20.0,
            "weight_percent": 100.0,
        }
    ],
}


async def _client() -> AsyncClient:
    app.state.API_KEY = ""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_history_returns_series_for_requested_range():
    history = {
        "range": "1M",
        "points": [
            {
                "t": "2026-01-02",
                "value": 1100.0,
                "cost_basis": 1000.0,
                "pnl": 100.0,
                "pnl_percent": 10.0,
                "source": "reconstructed",
            }
        ],
        "cost_basis": 1000.0,
        "start_value": 1100.0,
        "end_value": 1100.0,
        "change": 0.0,
        "change_percent": 0.0,
        "missing_symbols": [],
    }

    with (
        patch(
            "app.api.main.resolve_holdings",
            new_callable=AsyncMock,
            return_value=("manual", _HOLDINGS),
        ),
        patch(
            "app.api.main.value_holdings",
            new_callable=AsyncMock,
            return_value=_VALUATION,
        ),
        patch(
            "app.api.main.build_value_history",
            new_callable=AsyncMock,
            return_value=history,
        ) as build,
        patch.object(
            main.PORTFOLIO_REPO,
            "list_snapshots",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        async with await _client() as client:
            r = await client.get("/api/portfolio/history?range=1m")

    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "manual"
    assert body["range"] == "1M"
    assert body["holdings"] == ["AAPL"]
    assert body["totals"]["market_value"] == 1200.0
    assert body["points"][0]["source"] == "reconstructed"
    assert "1M" in body["available_ranges"]
    # The normalized range key is what reaches the builder.
    assert build.await_args.args[1] == "1M"


async def test_history_falls_back_to_default_range_for_unknown_input():
    with (
        patch(
            "app.api.main.resolve_holdings",
            new_callable=AsyncMock,
            return_value=("manual", _HOLDINGS),
        ),
        patch(
            "app.api.main.value_holdings",
            new_callable=AsyncMock,
            return_value=_VALUATION,
        ),
        patch(
            "app.api.main.build_value_history",
            new_callable=AsyncMock,
            return_value={"range": "3M", "points": []},
        ) as build,
        patch.object(
            main.PORTFOLIO_REPO,
            "list_snapshots",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        async with await _client() as client:
            r = await client.get("/api/portfolio/history?range=banana")

    assert r.status_code == 200
    assert build.await_args.args[1] == "3M"


async def test_history_returns_empty_payload_without_holdings():
    with patch(
        "app.api.main.resolve_holdings",
        new_callable=AsyncMock,
        return_value=("manual", []),
    ):
        async with await _client() as client:
            r = await client.get("/api/portfolio/history")

    assert r.status_code == 200
    body = r.json()
    assert body["points"] == []
    assert body["holdings"] == []
    assert body["start_value"] is None


_DIVERSIFICATION = {
    "sectors": [
        {
            "sector": "Technology",
            "market_value": 1200.0,
            "weight_percent": 100.0,
            "symbols": ["AAPL"],
        }
    ],
    "diversification": {
        "label": "concentrated",
        "tone": "bearish",
        "holding_hhi": 1.0,
        "effective_holdings": 1.0,
        "sector_hhi": 1.0,
        "effective_sectors": 1.0,
        "top_holding": {"symbol": "AAPL", "weight_percent": 100.0},
        "top_sector": {"sector": "Technology", "weight_percent": 100.0},
    },
}


async def test_insights_returns_positions_and_flattened_highlights():
    enriched = [
        {
            **_VALUATION["positions"][0],
            "stats": {
                "symbol": "AAPL",
                "from_ath_percent": -1.2,
                "flags": [
                    {"code": "near_ath", "label": "1.2% below ATH", "tone": "bullish"}
                ],
            },
        }
    ]

    with (
        patch(
            "app.api.main.resolve_holdings",
            new_callable=AsyncMock,
            return_value=("ibkr", _HOLDINGS),
        ),
        patch(
            "app.api.main.value_holdings",
            new_callable=AsyncMock,
            return_value=_VALUATION,
        ),
        patch(
            "app.api.main.build_asset_insights",
            new_callable=AsyncMock,
            return_value=enriched,
        ),
        patch(
            "app.api.main.build_diversification",
            new_callable=AsyncMock,
            return_value=_DIVERSIFICATION,
        ),
    ):
        async with await _client() as client:
            r = await client.get("/api/portfolio/insights")

    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "ibkr"
    assert body["positions"][0]["stats"]["from_ath_percent"] == -1.2
    assert body["highlights"] == [
        {
            "symbol": "AAPL",
            "code": "near_ath",
            "label": "1.2% below ATH",
            "tone": "bullish",
            "weight_percent": 100.0,
        }
    ]
    assert body["sectors"] == _DIVERSIFICATION["sectors"]
    assert body["diversification"] == _DIVERSIFICATION["diversification"]


async def test_insights_returns_empty_payload_without_holdings():
    with patch(
        "app.api.main.resolve_holdings",
        new_callable=AsyncMock,
        return_value=("manual", []),
    ):
        async with await _client() as client:
            r = await client.get("/api/portfolio/insights")

    assert r.status_code == 200
    body = r.json()
    assert body["positions"] == []
    assert body["highlights"] == []
    assert body["totals"]["positions"] == 0
    assert body["sectors"] == []
    assert body["diversification"]["label"] == "unrated"


async def test_portfolio_overview_endpoints_require_api_key():
    app.state.API_KEY = "secret"
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            history = await client.get("/api/portfolio/history")
            insights = await client.get("/api/portfolio/insights")
    finally:
        app.state.API_KEY = ""

    assert history.status_code == 401
    assert insights.status_code == 401
