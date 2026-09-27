"""Tests for /api/integrations/status."""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app

pytestmark = pytest.mark.asyncio


async def _client() -> AsyncClient:
    app.state.API_KEY = ""
    app.state.http_client = AsyncMock()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_integrations_status_reports_unconfigured_by_default(monkeypatch):
    monkeypatch.delenv("SIGNA_KEY", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_PERSONAL_USE", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("REDDIT_SECRET", raising=False)

    async with await _client() as client:
        response = await client.get("/api/integrations/status")

    assert response.status_code == 200
    assert response.json() == {"signa": False, "reddit": False}


async def test_integrations_status_reports_configured(monkeypatch):
    monkeypatch.setenv("SIGNA_KEY", "test-key")
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")

    async with await _client() as client:
        response = await client.get("/api/integrations/status")

    assert response.status_code == 200
    assert response.json() == {"signa": True, "reddit": True}


async def test_integrations_status_requires_api_key_when_set():
    app.state.API_KEY = "secret"
    app.state.http_client = AsyncMock()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/integrations/status")
        assert response.status_code == 401
    finally:
        app.state.API_KEY = ""
