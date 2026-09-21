"""Tests for /api/admin/access-emails."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.services import cloudflare_access

pytestmark = pytest.mark.asyncio


async def _client() -> AsyncClient:
    app.state.API_KEY = ""
    app.state.http_client = AsyncMock()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_list_access_emails():
    with patch.object(
        cloudflare_access,
        "list_allowed_emails",
        AsyncMock(return_value=["a@example.com"]),
    ):
        async with await _client() as client:
            response = await client.get("/api/admin/access-emails")

    assert response.status_code == 200
    assert response.json() == {"emails": ["a@example.com"]}


async def test_list_access_emails_unconfigured_returns_503():
    with patch.object(
        cloudflare_access,
        "list_allowed_emails",
        AsyncMock(
            side_effect=cloudflare_access.CloudflareAccessError("not configured")
        ),
    ):
        async with await _client() as client:
            response = await client.get("/api/admin/access-emails")

    assert response.status_code == 503
    assert response.json()["detail"] == "not configured"


async def test_add_access_email_normalizes_and_calls_service():
    with patch.object(
        cloudflare_access,
        "add_allowed_email",
        AsyncMock(return_value=["friend@example.com"]),
    ) as mock_add:
        async with await _client() as client:
            response = await client.post(
                "/api/admin/access-emails", json={"email": "  Friend@Example.com  "}
            )

    assert response.status_code == 200
    assert response.json() == {"emails": ["friend@example.com"]}
    assert mock_add.call_args.args[1] == "friend@example.com"


async def test_add_access_email_rejects_malformed_address():
    async with await _client() as client:
        response = await client.post(
            "/api/admin/access-emails", json={"email": "not-an-email"}
        )

    assert response.status_code == 422


async def test_remove_access_email():
    with patch.object(
        cloudflare_access, "remove_allowed_email", AsyncMock(return_value=[])
    ) as mock_remove:
        async with await _client() as client:
            response = await client.delete(
                "/api/admin/access-emails/friend@example.com"
            )

    assert response.status_code == 200
    assert response.json() == {"emails": []}
    assert mock_remove.call_args.args[1] == "friend@example.com"


async def test_access_emails_require_api_key_when_set():
    app.state.API_KEY = "secret"
    app.state.http_client = AsyncMock()
    try:
        with patch.object(
            cloudflare_access, "list_allowed_emails", AsyncMock(return_value=[])
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/admin/access-emails")
        assert response.status_code == 401
    finally:
        app.state.API_KEY = ""
