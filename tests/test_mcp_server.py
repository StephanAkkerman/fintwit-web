import json

import httpx
import pytest
from httpx import ASGITransport

from app import mcp_server
from app.api.main import app


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for name in (
        "FINTWIT_URL",
        "CF_ACCESS_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
        "FINTWIT_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(mcp_server, "_catalogue", {})


SPEC = {
    "paths": {
        "/api/posts": {
            "get": {
                "summary": "List Posts",
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "default": 200},
                    },
                    {
                        "name": "X-API-Key",
                        "in": "header",
                        "schema": {"type": "string"},
                    },
                ],
            }
        },
        "/api/reddit/trends/{symbol}/history": {
            "get": {
                "summary": "History",
                "parameters": [
                    {
                        "name": "symbol",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
            }
        },
        "/api/portfolio": {"post": {"summary": "Add"}},
        "/api/stream": {"get": {"summary": "Stream"}},
        "/api/admin/access-emails": {"get": {"summary": "Emails"}},
    }
}


def test_catalogue_keeps_only_readable_get_routes():
    endpoints = mcp_server.list_get_endpoints(SPEC)

    assert [e["path"] for e in endpoints] == [
        "/api/posts",
        "/api/reddit/trends/{symbol}/history",
    ]
    assert endpoints[0]["params"] == [
        {"name": "limit", "in": "query", "default": 200, "type": "integer"}
    ]
    assert endpoints[1]["params"][0]["required"] is True


def test_catalogue_from_the_real_app_schema():
    paths = [e["path"] for e in mcp_server.list_get_endpoints(app.openapi())]

    assert "/api/posts" in paths
    assert "/api/overview/mention-heat" in paths
    assert "/api/stream" not in paths
    assert not any(p.startswith("/api/admin") for p in paths)
    # The schema must sit under /api/ so the tunnel's nginx proxies it.
    assert app.openapi_url == mcp_server.OPENAPI_PATH


def test_match_endpoint_fills_path_templates():
    endpoints = mcp_server.list_get_endpoints(SPEC)

    assert mcp_server.match_endpoint(endpoints, "/api/reddit/trends/GME/history")
    assert mcp_server.match_endpoint(endpoints, "/api/reddit/trends/GME") is None
    assert mcp_server.match_endpoint(endpoints, "/api/stream") is None


def test_headers_carry_the_access_service_token(monkeypatch):
    assert mcp_server.request_headers() == {"Accept": "application/json"}

    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "id.access")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "secret")
    monkeypatch.setenv("FINTWIT_API_KEY", "k")

    headers = mcp_server.request_headers()
    assert headers["CF-Access-Client-Id"] == "id.access"
    assert headers["CF-Access-Client-Secret"] == "secret"
    assert headers["X-API-Key"] == "k"


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_get_validates_the_path_then_returns_json(monkeypatch):
    monkeypatch.setenv("FINTWIT_URL", "https://fintwit.example.com/")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        if request.url.path == "/api/openapi.json":
            return httpx.Response(200, json=SPEC)
        return httpx.Response(200, json=[{"id": 1}])

    async with _mock_client(handler) as client:
        body = await mcp_server.call_endpoint(client, "/api/posts", {"limit": 5})
        with pytest.raises(mcp_server.FintwitApiError, match="list_endpoints"):
            await mcp_server.call_endpoint(client, "/api/portfolio")
        with pytest.raises(mcp_server.FintwitApiError, match="params"):
            await mcp_server.call_endpoint(client, "/api/posts?limit=5")

    assert json.loads(body) == [{"id": 1}]
    assert str(seen[1]) == "https://fintwit.example.com/api/posts?limit=5"
    # The catalogue is cached, so later calls don't refetch the schema.
    assert sum(u.path == "/api/openapi.json" for u in seen) == 1


async def test_access_login_redirect_explains_the_service_token():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "https://team.cloudflareaccess.com/cdn-cgi/login"},
        )

    async with _mock_client(handler) as client:
        with pytest.raises(mcp_server.FintwitApiError, match="CF_ACCESS_CLIENT_ID"):
            await mcp_server.fetch_endpoints(client)


async def test_rejected_api_key_and_unreachable_host():
    async with _mock_client(lambda r: httpx.Response(401, json={})) as client:
        with pytest.raises(mcp_server.FintwitApiError, match="FINTWIT_API_KEY"):
            await mcp_server.fetch_endpoints(client)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    async with _mock_client(down) as client:
        with pytest.raises(mcp_server.FintwitApiError, match="Could not reach"):
            await mcp_server.fetch_endpoints(client)


def test_truncate_marks_cut_responses():
    assert mcp_server.truncate({"a": 1}) == '{"a": 1}'

    cut = mcp_server.truncate(list(range(1000)), limit=50)
    assert cut.startswith("[0, 1, 2")
    assert "truncated" in cut


async def test_tools_against_the_real_app(monkeypatch):
    """End to end through the MCP tool layer, with the app served in-process."""
    monkeypatch.setenv("FINTWIT_URL", "http://fintwit.test")
    transport = ASGITransport(app=app)
    real_client = httpx.AsyncClient

    def client_factory(**kwargs):
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(mcp_server.httpx, "AsyncClient", client_factory)

    listed = await mcp_server.mcp.call_tool("list_endpoints", {})
    catalogue = json.loads(listed.content[0].text)
    assert catalogue["base_url"] == "http://fintwit.test"
    assert any(e["path"] == "/api/integrations/status" for e in catalogue["endpoints"])

    result = await mcp_server.mcp.call_tool("get", {"path": "/api/integrations/status"})
    assert "signa" in json.loads(result.content[0].text)
