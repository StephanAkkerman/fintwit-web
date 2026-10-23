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
        "/api/research/indicators",
        "/api/research/technicals",
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
        if path == "/api/research/price-context":
            return httpx.Response(200, json=PRICE_CONTEXT)
        if path == "/api/research/indicators":
            return httpx.Response(
                200,
                json={
                    symbol: INDICATORS if symbol == "AAPL" else None
                    for symbol in params["symbols"].split(",")
                },
            )
        if path == "/api/research/valuation":
            if params["symbol"] == "MSFT":
                return httpx.Response(404, json={"detail": "No valuation data"})
            return httpx.Response(200, json=VALUATION)
        if path == "/api/research/trend-stage":
            return httpx.Response(200, json=TREND_STAGE)
        if path == "/api/research/analysts":
            if params["symbol"] == "MSFT":
                return httpx.Response(404, json={"detail": "No analyst data"})
            return httpx.Response(200, json=ANALYSTS)
        if path == "/api/signa/options-flow" and "symbol" not in params:
            return httpx.Response(200, json=MARKET_FLOW)
        return httpx.Response(200, json={"path": path})

    return handler


TREND_STAGE = {
    "symbol": "AAPL",
    "as_of": "2026-10-23",
    "stage": {
        "stage": 2,
        "name": "advancing",
        "weeks_in_stage": 29,
        "previous_stage": 3,
        "ma30w": 312.1,
        "price_vs_ma30w_percent": 11.2,
        "ma30w_slope_5w_percent": 5.0,
    },
    "vs_market": {
        "mansfield": 12.5,
        "mansfield_rising_4w": True,
        "outperformance_13w_pp": 10.4,
        "outperformance_26w_pp": 18.2,
    },
    "benchmark": "SPY",
    "sector": {
        "name": "Technology",
        "etf": "XLK",
        "stage": {"stage": 2, "name": "advancing"},
        "vs_market": {"mansfield": 5.9},
        "stock_vs_sector": {"mansfield": 5.8},
    },
}

ANALYSTS = {
    "symbol": "AAPL",
    "rating_changes": {
        "days": 90,
        "upgrades": 2,
        "downgrades": 0,
        "initiations": 1,
        "target_raises": 5,
        "target_cuts": 1,
        "recent_actions": [{"firm": f"F{i}"} for i in range(6)],
    },
    "recommendations": {"buy_percent": 75.0, "buy_percent_change_3m": 5.0},
    "estimates": {
        "direction": "rising",
        "periods": {"0y": {"change_30d_percent": 2.1, "up_30d": 9, "down_30d": 1}},
    },
}

MARKET_FLOW = {
    "symbol": None,
    "bias": "mixed",
    "top_bullish": [{"symbol": "AAPL"}],
    "top_large": [{"symbol": "AAPL"}],
    "by_symbol": {
        "AAPL": {
            "bias": "bullish",
            "scored_bullish_premium": 1_000_000,
            "scored_bearish_premium": 0,
            "call_premium": 2_000_000,
            "put_premium": 0,
            "top_scored": [{"strike": 300}],
            "top_large": [{"strike": 300}],
        }
    },
}


PRICE_CONTEXT = {
    "symbol": "AAPL",
    "stats": {
        "from_52w_high_percent": -4.0,
        "range_position_52w": 88.0,
        "from_ath_percent": -4.0,
        "flags": ["near_52w_high"],
        "all_time_high": {"value": 260.0, "t": "2026-09-01"},
    },
    "trend": {
        "returns_percent": {"1m": 3.0, "3m": 9.0, "6m": 12.0, "1y": 20.0},
        "sma_50": {"value": 240.0, "price_vs_percent": 4.0},
        "sma_200": {"value": 220.0, "price_vs_percent": 13.0},
        "trend": "uptrend",
    },
}

INDICATORS = {
    "symbol": "AAPL",
    "tv_symbol": "NASDAQ:AAPL",
    "price": 250.0,
    "rsi": {"value": 72.4, "state": "overbought", "four_h": 65.0},
    "macd": {"macd": 1.2, "signal": 0.9, "above_signal": True, "cross": None},
    "moving_averages": {
        "sma200": 220.0,
        "price_vs_sma20_percent": 2.0,
        "price_vs_sma50_percent": 4.0,
        "price_vs_sma200_percent": 13.6,
        "sma50_vs_sma200": "golden_cross",
        "cross_today": None,
    },
    "atr": {"value": 5.0, "percent_of_price": 2.0},
    "adx": {"value": 27.0, "trend_strength": "strong", "direction": "up"},
    "volume": {"today": 1, "avg_30d": 2, "vs_avg_30d": 0.5},
    "rating": {"one_d": "Buy", "four_h": "Strong Buy"},
    "signals": ["rsi_overbought", "above_sma200", "strong_uptrend"],
}

VALUATION = {
    "symbol": "AAPL",
    "fundamentals": {"forward_pe": 28.0, "market_cap": 3.8e12},
    "analysts": {"rating": "buy", "target_mean": 280.0, "upside_percent": 12.0},
    "short_interest": {"short_percent_of_float": 0.7},
}


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
    # The research views are trimmed to what a decision needs.
    assert aapl["price_context"] == {
        "from_52w_high_percent": -4.0,
        "range_position_52w": 88.0,
        "from_ath_percent": -4.0,
        "flags": ["near_52w_high"],
        "returns_percent": {"1m": 3.0, "3m": 9.0, "6m": 12.0, "1y": 20.0},
        "price_vs_sma_200_percent": 13.0,
        "trend": "uptrend",
    }
    assert aapl["analysts"] == {
        "rating": "buy",
        "target_mean": 280.0,
        "upside_percent": 12.0,
        "forward_pe": 28.0,
        "short_percent_of_float": 0.7,
    }
    assert aapl["technicals"] == {
        "rsi": 72.4,
        "macd_above_signal": True,
        "macd_cross": None,
        "price_vs_sma20_percent": 2.0,
        "price_vs_sma50_percent": 4.0,
        "price_vs_sma200_percent": 13.6,
        "sma50_vs_sma200": "golden_cross",
        "atr": 5.0,
        "atr_percent": 2.0,
        "adx": 27.0,
        "volume_vs_avg_30d": 0.5,
        "rating_1d": "Buy",
        "rating_4h": "Strong Buy",
        "signals": ["rsi_overbought", "above_sma200", "strong_uptrend"],
    }
    assert msft["technicals"] is None
    assert aapl["trend_stage"] == {
        "stage": 2,
        "stage_name": "advancing",
        "weeks_in_stage": 29,
        "previous_stage": 3,
        "price_vs_ma30w_percent": 11.2,
        "ma30w_slope_5w_percent": 5.0,
        "rs_vs_market": 12.5,
        "rs_vs_market_rising": True,
        "outperformance_13w_pp": 10.4,
        "sector_etf": "XLK",
        "sector_stage": 2,
        "sector_rs_vs_market": 5.9,
        "rs_vs_sector": 5.8,
    }
    assert aapl["analyst_activity"] == {
        "days": 90,
        "upgrades": 2,
        "downgrades": 0,
        "target_raises": 5,
        "target_cuts": 1,
        "latest_actions": [{"firm": "F0"}, {"firm": "F1"}, {"firm": "F2"}],
        "buy_percent": 75.0,
        "buy_percent_change_3m": 5.0,
        "eps_revisions": "rising",
        "eps_this_year_change_30d_percent": 2.1,
        "eps_this_year_up_30d": 9,
        "eps_this_year_down_30d": 1,
    }
    assert "404" in msft["analyst_activity"]["error"]
    # One market-wide flow request, sliced per holding.
    assert [p for p, _ in seen].count("/api/signa/options-flow") == 1
    assert aapl["options_flow"] == {
        "bias": "bullish",
        "scored_bullish_premium": 1_000_000,
        "scored_bearish_premium": 0,
        "call_premium": 2_000_000,
        "put_premium": 0,
        "top_scored": [{"strike": 300}],
    }
    assert msft["options_flow"]["bias"] is None
    # All holdings share one indicators request.
    assert [p for p, _ in seen].count("/api/research/indicators") == 1
    assert ("/api/research/indicators", {"symbols": "AAPL,MSFT"}) in seen
    assert "404" in msft["analysts"]["error"]
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
    assert result["your_position"] == [{"symbol": "AAPL", "market_value": 2000.0}]
    assert "404" in result["gamma_exposure"]["error"]
    assert "earnings_calendar" not in result
    assert ("/api/reddit/trends/AAPL/history", {"days": "30"}) in seen
    # The full research views, not the holdings_check summaries.
    assert result["price_context"] == PRICE_CONTEXT
    assert result["valuation"] == VALUATION
    assert (
        "/api/research/technicals",
        {"symbol": "AAPL", "asset_kind": "stock"},
    ) in seen
    assert result["trend_stage"] == TREND_STAGE
    assert result["analyst_activity"] == ANALYSTS
    assert ("/api/signa/options-flow", {"symbol": "AAPL"}) in seen
    assert ("/api/signa/dark-pool", {"symbol": "AAPL"}) in seen


def _market_handler(seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        path, params = request.url.path, dict(request.url.params)
        seen.append((request.method, path, params, request.content))
        if path == "/api/markets/movers":
            return httpx.Response(
                200, json={"category": params["category"], "movers": list(range(25))}
            )
        if path == "/api/advisor/strategy":
            return httpx.Response(200, json={"rules": "", "watchlist": ["NVDA", "AMD"]})
        if path == "/api/portfolio/insights":
            return httpx.Response(200, json={"positions": [{"symbol": "nvda"}]})
        if path == "/api/overview/ticker-timeseries":
            return httpx.Response(200, json={"points": [], "summary": {"total": 1}})
        if path == "/api/fear-greed":
            return httpx.Response(503, json={"detail": "down"})
        if path == "/api/stocks/insider-trades":
            clusters = [{"ticker": f"T{i}"} for i in range(15)]
            return httpx.Response(
                200,
                json={
                    "trades": [{"ticker": "T0"}],
                    "summary": {"cluster_buys": clusters, "top_buys": clusters[:2]},
                },
            )
        if path == "/api/stocks/fund-holdings":
            return httpx.Response(
                200,
                json={
                    "funds": [{"name": "Big Fund"}],
                    "report_date": "2026-06-30",
                    "most_bought": [{"ticker": "GOOGL"}],
                },
            )
        if path == "/api/signa/options-flow":
            return httpx.Response(200, json=MARKET_FLOW)
        if path == "/api/research/trend-stage":
            return httpx.Response(200, json=TREND_STAGE)
        if path == "/api/advisor/calls" and request.method == "POST":
            return httpx.Response(201, json={"id": 7, **json.loads(request.content)})
        return httpx.Response(200, json={"path": path})

    return handler


async def test_market_snapshot_trims_movers_and_keeps_failures():
    async with _mock_client(_market_handler([])) as client:
        result = json.loads(await mcp_server.collect_market_snapshot(client))

    assert result["gainers"]["movers"] == list(range(10))
    assert result["losers"]["category"] == "losers"
    assert "503" in result["crypto_fear_greed"]["error"]
    assert result["market_hours"] == {"path": "/api/stocks/market-hours"}
    assert result["positioning"] == {"path": "/api/market/positioning"}
    assert result["breadth"] == {"path": "/api/market/breadth"}
    assert result["world_indices"] == {"path": "/api/market/world-indices"}


async def test_candidates_flags_held_watchlist_symbols():
    seen = []
    async with _mock_client(_market_handler(seen)) as client:
        result = json.loads(await mcp_server.collect_candidates(client))

    assert result["held_symbols"] == ["NVDA"]
    assert [(w["symbol"], w["held"]) for w in result["watchlist"]] == [
        ("NVDA", True),
        ("AMD", False),
    ]
    assert result["watchlist"][0]["tweets"] == {"total": 1}
    assert "strategy" not in result and "positions" not in result
    assert len(result["insider_buying"]["cluster_buys"]) == 10
    assert result["insider_buying"]["top_buys"] == [{"ticker": "T0"}, {"ticker": "T1"}]
    assert result["fund_buying"] == {
        "report_date": "2026-06-30",
        "most_bought": [{"ticker": "GOOGL"}],
    }
    assert any(
        p == "/api/overview/hidden-gems" and q["asset_kind"] == "equity"
        for _, p, q, _ in seen
    )
    # The market-wide ranking, without the per-symbol breakdown.
    assert result["options_flow"] == {
        "symbol": None,
        "bias": "mixed",
        "top_bullish": [{"symbol": "AAPL"}],
    }
    assert result["watchlist"][1]["trend_stage"]["stage"] == 2


async def test_log_call_and_journal():
    seen = []
    async with _mock_client(_market_handler(seen)) as client:
        logged = json.loads(
            await mcp_server.log_journal_call(
                client, {"symbol": "NVDA", "action": "buy", "reasoning": "r"}
            )
        )
        journal = json.loads(
            await mcp_server.collect_journal(client, 5, "$nvda", since_hours=6)
        )

    assert logged["id"] == 7
    assert (
        "GET",
        "/api/advisor/calls",
        {"limit": "5", "symbol": "NVDA", "since_hours": "6"},
    ) in [s[:3] for s in seen]
    assert set(journal) == {"scorecard", "calls"}


async def test_followed_traders_tool(monkeypatch):
    seen = []

    async def fake_request(client, path, params, body=None, *, method="GET"):
        seen.append((path, params))
        return {"leads": [{"symbol": "GTLB"}]}

    monkeypatch.setattr(mcp_server, "_request", fake_request)
    called = await mcp_server.mcp.call_tool("followed_traders", {"since_hours": 10_000})
    result = json.loads(called.content[0].text)

    assert result == {"leads": [{"symbol": "GTLB"}]}
    assert seen == [("/api/advisor/followed-mentions", {"since_hours": 720})]


async def test_unseen_posts_and_finish_check_tools(monkeypatch):
    seen = []

    async def fake_request(client, path, params, body=None, *, method="GET"):
        seen.append((method, path, params, body))
        return {"ok": True}

    monkeypatch.setattr(mcp_server, "_request", fake_request)
    await mcp_server.mcp.call_tool("unseen_posts", {})
    await mcp_server.mcp.call_tool(
        "finish_check",
        {"cursor": "102", "summary": "Nothing new", "session": "Open", "posts_read": 3},
    )

    assert seen == [
        ("GET", "/api/advisor/unseen-posts", {"limit": 40}, None),
        (
            "POST",
            "/api/advisor/runs",
            None,
            {
                "cursor": "102",
                "summary": "Nothing new",
                "session": "Open",
                "posts_read": 3,
            },
        ),
    ]


def test_generic_get_cannot_write_the_journal_or_strategy():
    endpoints = mcp_server.list_readable_endpoints(app.openapi())
    calls = mcp_server.match_endpoint(endpoints, "/api/advisor/calls")
    # Listed as a read (GET); the POST is only reachable through log_call.
    assert calls is not None and calls.get("method", "GET") == "GET"
    strategy = mcp_server.match_endpoint(endpoints, "/api/advisor/strategy")
    assert strategy.get("method", "GET") == "GET"
