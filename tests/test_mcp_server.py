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
        "/api/traders/credibility": {
            "post": {
                "summary": "Credibility Batch",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Batch"}
                        }
                    }
                },
            }
        },
        "/api/stream": {"get": {"summary": "Stream"}},
        "/api/admin/access-emails": {"get": {"summary": "Emails"}},
    },
    "components": {
        "schemas": {
            "Batch": {
                "title": "Batch",
                "type": "object",
                "properties": {
                    "screen_names": {"type": "array", "items": {"type": "string"}}
                },
            }
        }
    },
}


def test_catalogue_keeps_only_readable_get_routes():
    endpoints = mcp_server.list_readable_endpoints(SPEC)

    assert [e["path"] for e in endpoints] == [
        "/api/posts",
        "/api/reddit/trends/{symbol}/history",
        "/api/traders/credibility",
    ]
    assert endpoints[2]["method"] == "POST"
    assert endpoints[2]["body"] == {
        "type": "object",
        "properties": {"screen_names": {"type": "array", "items": {"type": "string"}}},
    }
    assert endpoints[0]["params"] == [
        {"name": "limit", "in": "query", "default": 200, "type": "integer"}
    ]
    assert endpoints[1]["params"][0]["required"] is True


def test_catalogue_from_the_real_app_schema():
    paths = [e["path"] for e in mcp_server.list_readable_endpoints(app.openapi())]

    assert "/api/posts" in paths
    assert "/api/overview/mention-heat" in paths
    assert "/api/portfolio/summary" in paths
    assert "/api/stream" not in paths
    assert not any(p.startswith("/api/admin") for p in paths)
    # Every read-only POST must still exist, or its lookup silently vanishes.
    assert mcp_server.READ_ONLY_POSTS <= set(paths)
    assert set(mcp_server.PORTFOLIO_PATHS) <= set(paths)
    # Every endpoint the holdings_check and ticker bundles call.
    assert {
        "/api/portfolio/insights",
        "/api/overview/ticker-timeseries",
        "/api/overview/ticker-price-history",
        "/api/reddit/trends/{symbol}/history",
        "/api/news/company",
        "/api/options/overview",
        "/api/options/gamma-exposure",
        "/api/earnings/calendar",
    } <= set(paths)
    # The schema must sit under /api/ so the tunnel's nginx proxies it.
    assert app.openapi_url == mcp_server.OPENAPI_PATH


def test_match_endpoint_fills_path_templates():
    endpoints = mcp_server.list_readable_endpoints(SPEC)

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
    monkeypatch.setenv("FINTWIT_API_KEY", "mcp-key")
    monkeypatch.setattr(app.state, "API_KEY", "mcp-key", raising=False)
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


async def test_read_only_post_sends_the_body():
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/openapi.json":
            return httpx.Response(200, json=SPEC)
        sent.append((request.method, json.loads(request.content or b"null")))
        return httpx.Response(200, json={"finguru": {"score": 0.7}})

    async with _mock_client(handler) as client:
        body = await mcp_server.call_endpoint(
            client, "/api/traders/credibility", body={"screen_names": ["finguru"]}
        )
        with pytest.raises(mcp_server.FintwitApiError, match="no body"):
            await mcp_server.call_endpoint(client, "/api/posts", body={"x": 1})

    assert json.loads(body) == {"finguru": {"score": 0.7}}
    assert sent == [("POST", {"screen_names": ["finguru"]})]


async def test_portfolio_keeps_going_when_one_view_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/ibkr/"):
            return httpx.Response(503, json={"detail": "IBKR sync is disabled"})
        return httpx.Response(200, json={"path": request.url.path})

    async with _mock_client(handler) as client:
        result = json.loads(await mcp_server.collect_portfolio(client))

    assert result["portfolio_summary"] == {"path": "/api/portfolio/summary"}
    assert "IBKR sync is disabled" in result["ibkr_account"]["error"]
    assert len(result) == len(mcp_server.PORTFOLIO_PATHS)


CALENDAR = {
    "days": [
        {"date": "2026-10-12", "rows": [{"symbol": "AAPL", "time": "amc"}]},
        {"date": "2026-10-13", "rows": [{"symbol": "TSLA", "time": "bmo"}]},
    ]
}


def _bundle_handler(seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        path, params = request.url.path, dict(request.url.params)
        seen.append((path, params))
        if path == "/api/portfolio/insights":
            return httpx.Response(
                200,
                json={
                    "source": "manual",
                    "totals": {"market_value": 3000.0},
                    "diversification": {"label": "concentrated"},
                    "positions": [
                        {"symbol": "MSFT", "market_value": 1000.0},
                        {"symbol": "AAPL", "market_value": 2000.0},
                    ],
                },
            )
        if path == "/api/overview/ticker-timeseries":
            return httpx.Response(
                200,
                json={"points": [1, 2, 3], "summary": {"total_mentions": 4}},
            )
        if path.startswith("/api/reddit/trends/"):
            return httpx.Response(200, json={"points": [{"rank": 9}, {"rank": 3}]})
        if path == "/api/news/company":
            if params["symbols"] == "MSFT":
                return httpx.Response(503, json={"detail": "Service Unavailable"})
            return httpx.Response(200, json={"articles": [{"title": "Beat"}]})
        if path == "/api/earnings/calendar":
            return httpx.Response(200, json=CALENDAR)
        if path == "/api/options/gamma-exposure":
            return httpx.Response(404, json={"detail": "no options"})
        if path == "/api/portfolio/positions":
            return httpx.Response(
                200, json=[{"symbol": "aapl", "quantity": 5}, {"symbol": "MSFT"}]
            )
        return httpx.Response(200, json={"path": path})

    return handler


async def test_holdings_check_joins_every_view_per_holding():
    seen = []
    async with _mock_client(_bundle_handler(seen)) as client:
        result = json.loads(await mcp_server.collect_holdings_check(client, 24))

    assert result["totals"] == {"market_value": 3000.0}
    # Largest holding first.
    assert [h["symbol"] for h in result["holdings"]] == ["AAPL", "MSFT"]
    aapl, msft = result["holdings"]
    assert aapl["tweets"] == {"total_mentions": 4}  # summary only, no buckets
    assert aapl["reddit_latest"] == {"rank": 3}
    assert aapl["news"] == {"articles": [{"title": "Beat"}]}
    assert aapl["earnings"] == [{"date": "2026-10-12", "symbol": "AAPL", "time": "amc"}]
    # One failing view leaves the rest of that holding intact.
    assert "503" in msft["news"]["error"]
    assert msft["earnings"] == []
    assert (
        "/api/overview/ticker-timeseries",
        {"ticker": "AAPL", "window_hours": "24"},
    ) in seen


async def test_holdings_check_caps_large_portfolios(monkeypatch):
    monkeypatch.setattr(mcp_server, "MAX_HOLDINGS", 1)
    async with _mock_client(_bundle_handler([])) as client:
        result = json.loads(await mcp_server.collect_holdings_check(client))

    assert [h["symbol"] for h in result["holdings"]] == ["AAPL"]
    assert result["not_checked"] == ["MSFT"]


async def test_ticker_bundle():
    seen = []
    async with _mock_client(_bundle_handler(seen)) as client:
        result = json.loads(await mcp_server.collect_ticker(client, "$aapl"))
        with pytest.raises(mcp_server.FintwitApiError, match="ticker symbol"):
            await mcp_server.collect_ticker(client, "../admin")

    assert result["symbol"] == "AAPL"
    assert result["mentions"]["points"] == [1, 2, 3]  # full series here
    assert result["earnings"] == [
        {"date": "2026-10-12", "symbol": "AAPL", "time": "amc"}
    ]
    assert result["your_position"] == [{"symbol": "aapl", "quantity": 5}]
    assert "404" in result["gamma_exposure"]["error"]
    assert "earnings_calendar" not in result
    assert ("/api/reddit/trends/AAPL/history", {"days": "30"}) in seen
