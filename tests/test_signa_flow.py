import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.signa_flow as signa_flow
from app.services.signa import SignaClient, _decode_tool_result

HEADERS = {"X-API-Key": "test-api-key"}


def _curated(symbol, direction, option_type, premium, conviction=60):
    return {
        "conviction_score": conviction,
        "direction": direction,
        "confirms_signal": True,
        "rationale_short": f"{direction} {option_type}",
        "scored_at": "2026-10-23T15:00:00+00:00",
        "flow_events": {
            "symbol": symbol,
            "option_type": option_type,
            "strike": 100,
            "expiry": "2026-11-20",
            "dte": 28,
            "premium_size": premium,
            "is_sweep": True,
            "is_block": False,
            "timestamp": "2026-10-23T14:58:00+00:00",
        },
    }


def _raw(symbol, option_type, sentiment, premium):
    return {
        "symbol": symbol,
        "option_type": option_type,
        "sentiment": sentiment,
        "strike": 100,
        "expiry": "2026-11-20",
        "dte": 28,
        "premium_size": premium,
        "is_sweep": False,
        "is_block": True,
        "volume_oi_ratio": 2.5,
        "executed_at": "2026-10-23T16:00:00+00:00",
    }


CURATED = {
    "events": [
        _curated("MU", "BULLISH", "CALL", 3_000_000),
        _curated("MU", "BULLISH", "PUT", 1_000_000),
        _curated("HWM", "BEARISH", "PUT", 2_000_000),
        _curated("NVDA", "BULLISH", "CALL", 500_000),
        _curated("NVDA", "BEARISH", "CALL", 400_000),
    ]
}
RAW = {
    "events": [
        _raw("MU", "CALL", "BULLISH", 4_000_000),
        _raw("TSLA", "CALL", "BULLISH", 2_500_000),
        _raw("TSLA", "PUT", "BEARISH", 300_000),
    ]
}


def _patch_tools(monkeypatch, curated=CURATED, raw=RAW, dark=None):
    calls = []

    async def call_tool(name, arguments=None):
        calls.append((name, arguments))
        return {
            "get_curated_flow": curated,
            "get_raw_flow": raw,
            "get_dark_pool": dark,
        }[name]

    monkeypatch.setattr(signa_flow._client, "call_tool", call_tool)
    return calls


async def test_market_wide_flow_ranks_symbols(monkeypatch):
    calls = _patch_tools(monkeypatch)

    result = await signa_flow.get_options_flow()

    assert [name for name, _ in calls] == ["get_curated_flow", "get_raw_flow"]
    assert calls[1][1] == {"limit": 200, "min_premium": 250_000}
    assert result["symbol"] is None
    assert result["top_bullish"][0] == {
        "symbol": "MU",
        "scored_bullish_premium": 4_000_000,
        "bias": "bullish",
    }
    assert [r["symbol"] for r in result["top_bearish"]] == ["HWM", "NVDA"]
    assert [r["symbol"] for r in result["top_call_buying"]] == ["MU", "TSLA"]

    mu = result["by_symbol"]["MU"]
    assert (mu["call_premium"], mu["put_premium"]) == (4_000_000, 0)
    assert len(mu["top_scored"]) == 2
    # Bullish and bearish within 2x of each other: mixed.
    assert result["by_symbol"]["NVDA"]["bias"] == "mixed"
    # Nothing scored for TSLA: bias falls back to the raw sentiment.
    assert result["by_symbol"]["TSLA"]["bias"] == "bullish"
    assert result["by_symbol"]["TSLA"]["scored_trades"] == 0


async def test_single_symbol_flow(monkeypatch):
    calls = _patch_tools(monkeypatch)

    result = await signa_flow.get_options_flow("mu")

    assert calls[0][1] == {"limit": 100, "symbol": "MU"}
    assert result["symbol"] == "MU"
    assert "by_symbol" not in result
    assert result["scored_bullish"] == 2
    assert result["top_scored"][0]["premium"] == 3_000_000
    assert result["top_scored"][0]["rationale"] == "BULLISH CALL"


async def test_flow_is_none_only_when_both_feeds_fail(monkeypatch):
    _patch_tools(monkeypatch, curated=None, raw=None)
    assert await signa_flow.get_options_flow() is None

    _patch_tools(monkeypatch, curated=None)
    result = await signa_flow.get_options_flow()
    assert result["curated_available"] is False
    assert result["large_trades"] == 3


async def test_dark_pool_lean(monkeypatch):
    def print_(price, size, bid, ask, canceled=False):
        return {
            "ticker": "NVDA",
            "price": str(price),
            "size": size,
            "premium": str(price * size),
            "nbbo_bid": str(bid),
            "nbbo_ask": str(ask),
            "executed_at": f"2026-10-23T16:{size % 60:02d}:00Z",
            "canceled": canceled,
        }

    dark = {
        "prints": [
            print_(100.0, 5000, 99.98, 100.0),  # at the ask
            print_(99.98, 1000, 99.98, 100.0),  # at the bid
            print_(99.99, 1000, 99.98, 100.0),  # mid
            print_(100.0, 9999, 99.98, 100.0, canceled=True),
        ]
    }
    _patch_tools(monkeypatch, dark=dark)

    result = await signa_flow.get_dark_pool("nvda")

    assert result["prints"] == 3
    assert result["notional"] == 699_970
    assert result["at_or_above_ask_notional"] == 500_000
    assert result["at_or_below_bid_notional"] == 99_980
    assert result["lean"] == "buyers"
    assert result["largest"][0]["notional"] == 500_000

    _patch_tools(monkeypatch, dark=None)
    assert await signa_flow.get_dark_pool("NVDA") is None


def test_decode_tool_result_plain_and_sse():
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"content": [{"type": "text", "text": json.dumps({"a": 1})}]},
    }
    assert _decode_tool_result(json.dumps(body)) == {"a": 1}
    sse = f"event: message\ndata: {json.dumps(body)}\n\n"
    assert _decode_tool_result(sse) == {"a": 1}

    body["result"]["isError"] = True
    assert _decode_tool_result(json.dumps(body)) is None
    assert _decode_tool_result("not json") is None


async def test_call_tool_posts_json_rpc_and_caches():
    body = {"result": {"content": [{"text": json.dumps({"events": []})}]}}
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.text = AsyncMock(return_value=json.dumps(body))
    post_cm = MagicMock()
    post_cm.__aenter__ = AsyncMock(return_value=response)
    post_cm.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.post = MagicMock(return_value=post_cm)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    client = SignaClient(api_key="test-key")
    with patch(
        "app.services.signa.aiohttp.ClientSession", MagicMock(return_value=session)
    ):
        first = await client.call_tool("get_curated_flow", {"limit": 5})
        second = await client.call_tool("get_curated_flow", {"limit": 5})

    assert first == second == {"events": []}
    session.post.assert_called_once()
    call = session.post.call_args
    assert call.args[0] == "https://app.getsigna.ai/api/mcp"
    assert call.kwargs["json"]["params"] == {
        "name": "get_curated_flow",
        "arguments": {"limit": 5},
    }
    assert call.kwargs["headers"]["Authorization"] == "Bearer test-key"


async def test_call_tool_needs_a_key(monkeypatch):
    monkeypatch.delenv("SIGNA_KEY", raising=False)
    assert await SignaClient().call_tool("get_dark_pool") is None


@pytest.mark.parametrize("path", ["/api/signa/options-flow", "/api/signa/dark-pool"])
async def test_flow_endpoints_need_the_key(async_client, monkeypatch, path):
    monkeypatch.delenv("SIGNA_KEY", raising=False)
    resp = await async_client.get(path, params={"symbol": "NVDA"}, headers=HEADERS)
    assert resp.status_code == 503
    assert "SIGNA_KEY" in resp.json()["detail"]


async def test_flow_endpoints(async_client, monkeypatch):
    import app.api.main as main

    monkeypatch.setenv("SIGNA_KEY", "k")
    seen = []

    async def flow(symbol):
        seen.append(symbol)
        return {"symbol": symbol}

    async def dark(symbol):
        return None

    monkeypatch.setattr(main, "get_options_flow", flow)
    monkeypatch.setattr(main, "get_dark_pool", dark)

    resp = await async_client.get("/api/signa/options-flow", headers=HEADERS)
    assert resp.json() == {"symbol": None}
    resp = await async_client.get(
        "/api/signa/options-flow", params={"symbol": "MU"}, headers=HEADERS
    )
    assert resp.json() == {"symbol": "MU"}
    assert seen == [None, "MU"]
    resp = await async_client.get(
        "/api/signa/dark-pool", params={"symbol": "MU"}, headers=HEADERS
    )
    assert resp.status_code == 503
