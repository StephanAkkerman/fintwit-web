from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

import app.services.signa as signa_service
from app.services.signa import SignaClient, get_signa_live_feed, get_signa_signal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resp(status: int, payload: dict[str, Any] | list[Any]) -> MagicMock:
    """Mock aiohttp response as an async context manager."""
    response = MagicMock()
    response.status = status
    response.json = AsyncMock(return_value=payload)
    response.raise_for_status = MagicMock()
    if status >= 400:
        response.raise_for_status.side_effect = aiohttp.ClientResponseError(
            request_info=MagicMock(), history=(), status=status
        )
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _session(get_mock: MagicMock) -> MagicMock:
    """Mock aiohttp.ClientSession factory wrapping a prepared ``get`` mock."""
    session = MagicMock()
    session.get = get_mock
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=session)


def _assert_call(call: Any, *, url: str, params: dict[str, Any] | None) -> None:
    assert call.args[0] == url
    assert call.kwargs["params"] == params
    assert call.kwargs["headers"]["Authorization"] == "Bearer test-key"


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------


async def test_signa_client_covers_all_requested_endpoints():
    get_mock = MagicMock(side_effect=lambda *a, **k: _resp(200, {"ok": True}))
    client = SignaClient(api_key="test-key")

    with patch("app.services.signa.aiohttp.ClientSession", _session(get_mock)):
        assert await client.get_signal("aapl") is not None
        assert await client.get_quote("aapl") is not None
        assert await client.get_history("aapl") is not None
        assert await client.get_enhanced_signal("aapl") is not None
        assert await client.get_signal_index() is not None
        assert await client.scan(signal="bullish", min_score=70) is not None
        assert await client.get_me() is not None

    calls = get_mock.call_args_list
    assert len(calls) == 7
    _assert_call(
        calls[0], url="https://app.getsigna.ai/api/v1/signal", params={"sym": "AAPL"}
    )
    _assert_call(calls[1], url="https://app.getsigna.ai/api/v1/quote/AAPL", params=None)
    _assert_call(
        calls[2], url="https://app.getsigna.ai/api/v1/history/AAPL", params=None
    )
    _assert_call(
        calls[3],
        url="https://app.getsigna.ai/api/v1/enhanced-signal",
        params={"sym": "AAPL"},
    )
    _assert_call(
        calls[4], url="https://app.getsigna.ai/api/v1/signal-index", params=None
    )
    _assert_call(
        calls[5],
        url="https://app.getsigna.ai/api/v1/scan",
        params={"signal": "bullish", "min_score": 70},
    )
    _assert_call(calls[6], url="https://app.getsigna.ai/api/v1/me", params=None)


async def test_signa_client_returns_none_for_empty_ticker():
    client = SignaClient(api_key="test-key")

    assert await client.get_signal("") is None
    assert await client.get_quote("   ") is None
    assert await client.get_history("") is None
    assert await client.get_enhanced_signal("") is None


async def test_signa_client_returns_none_on_request_error():
    get_mock = MagicMock(side_effect=aiohttp.ClientError("network down"))
    client = SignaClient(api_key="test-key")

    with patch("app.services.signa.aiohttp.ClientSession", _session(get_mock)):
        assert await client.get_me() is None


async def test_signa_client_returns_none_on_http_error():
    get_mock = MagicMock(side_effect=lambda *a, **k: _resp(500, {"ok": False}))
    client = SignaClient(api_key="test-key")

    with patch("app.services.signa.aiohttp.ClientSession", _session(get_mock)):
        assert await client.get_me() is None


async def test_signa_client_cache_hit_skips_second_network_call():
    counter = {"n": 0}

    def _get(*a: Any, **k: Any) -> MagicMock:
        counter["n"] += 1
        return _resp(200, {"ok": True, "value": counter["n"]})

    get_mock = MagicMock(side_effect=_get)
    now = {"value": 1000.0}
    client = SignaClient(
        api_key="test-key", cache_ttl_seconds=60, time_fn=lambda: now["value"]
    )

    with patch("app.services.signa.aiohttp.ClientSession", _session(get_mock)):
        first = await client.get_quote("aapl")
        second = await client.get_quote("aapl")

    assert first == second
    assert get_mock.call_count == 1


async def test_signa_client_cache_ttl_expiry_refetches():
    counter = {"n": 0}

    def _get(*a: Any, **k: Any) -> MagicMock:
        counter["n"] += 1
        return _resp(200, {"ok": True, "value": counter["n"]})

    get_mock = MagicMock(side_effect=_get)
    now = {"value": 2000.0}
    client = SignaClient(
        api_key="test-key", cache_ttl_seconds=10, time_fn=lambda: now["value"]
    )

    with patch("app.services.signa.aiohttp.ClientSession", _session(get_mock)):
        first = await client.get_quote("aapl")
        now["value"] += 11
        second = await client.get_quote("aapl")

    assert first != second
    assert get_mock.call_count == 2


async def test_signa_client_enforces_per_minute_limit():
    get_mock = MagicMock(side_effect=lambda *a, **k: _resp(200, {"ok": True}))
    now = {"value": 3000.0}
    client = SignaClient(
        api_key="test-key",
        cache_ttl_seconds=0,
        per_minute_limit=2,
        per_day_limit=1000,
        time_fn=lambda: now["value"],
    )

    with patch("app.services.signa.aiohttp.ClientSession", _session(get_mock)):
        assert await client.get_quote("aapl") is not None
        assert await client.get_quote("msft") is not None
        assert await client.get_quote("nvda") is None

    assert get_mock.call_count == 2


async def test_signa_client_enforces_per_day_limit():
    get_mock = MagicMock(side_effect=lambda *a, **k: _resp(200, {"ok": True}))
    now = {"value": 4000.0}
    client = SignaClient(
        api_key="test-key",
        cache_ttl_seconds=0,
        per_minute_limit=100,
        per_day_limit=2,
        time_fn=lambda: now["value"],
    )

    with patch("app.services.signa.aiohttp.ClientSession", _session(get_mock)):
        assert await client.get_quote("aapl") is not None
        now["value"] += 61
        assert await client.get_quote("msft") is not None
        now["value"] += 61
        assert await client.get_quote("nvda") is None

    assert get_mock.call_count == 2


# ---------------------------------------------------------------------------
# get_signa_signal normalization
# ---------------------------------------------------------------------------


# NOTE: these payloads mirror the *actual* ``/api/v1/signal`` response. The
# verdict lives in ``engine.direction`` (the nightly consensus), NOT in the
# top-level ``signa`` key — which is a nested grade/action object.


def _real_signal_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "symbol": "AAPL",
        "timeframe": "1d",
        "engine": {
            "direction": "BULLISH",
            "score": 98,
            "confidence": 92,
            "grade": "A",
            "modelCount": 6,
        },
        # The top-level "signa" is an object, not the verdict label.
        "signa": {"grade": "B+", "conviction": 73, "action": "BUY"},
        "data": {"direction": "WAIT", "bias": "bullish", "confidence": 55},
    }


async def test_get_signa_signal_normalizes_payload():
    with patch.object(
        signa_service._default_client,
        "get_signal",
        new=AsyncMock(return_value=_real_signal_payload()),
    ):
        result = await get_signa_signal("aapl")

    assert result == {
        "source": "signa",
        "symbol": "AAPL",
        "signal": "Bullish",  # title-cased from "BULLISH"
        "score": 98.0,
        "trend": "bullish",
        "confidence": 0.92,  # 92 (0-100) normalized to 0-1
        "grade": "A",
        "timeframe": "1d",
        "website": "https://app.getsigna.ai/?sym=AAPL",
    }


async def test_get_signa_signal_ignores_nested_signa_object_as_label():
    """Regression: the object-shaped top-level ``signa`` must not be the verdict."""
    payload = {
        "ok": True,
        "symbol": "AAPL",
        "signa": {"grade": "B+", "action": "BUY"},
        # No engine / data verdict -> nothing usable.
    }
    with patch.object(
        signa_service._default_client,
        "get_signal",
        new=AsyncMock(return_value=payload),
    ):
        assert await get_signa_signal("AAPL") is None


async def test_get_signa_signal_falls_back_to_data_bias_when_engine_absent():
    payload = {
        "ok": True,
        "symbol": "AAPL",
        "data": {"bias": "bearish", "confidence": 40},
    }
    with patch.object(
        signa_service._default_client,
        "get_signal",
        new=AsyncMock(return_value=payload),
    ):
        result = await get_signa_signal("AAPL")

    assert result is not None
    assert result["signal"] == "Bearish"
    assert result["confidence"] == 0.40
    assert result["score"] is None
    assert result["grade"] is None


async def test_get_signa_signal_keeps_fractional_confidence_as_is():
    """A confidence already on a 0-1 scale must not be divided again."""
    payload = {
        "ok": True,
        "symbol": "AAPL",
        "engine": {"direction": "BULLISH", "score": 80, "confidence": 0.81},
    }
    with patch.object(
        signa_service._default_client,
        "get_signal",
        new=AsyncMock(return_value=payload),
    ):
        result = await get_signa_signal("AAPL")

    assert result is not None
    assert result["confidence"] == 0.81


async def test_get_signa_signal_returns_none_without_label():
    payload = {"ok": True, "symbol": "AAPL", "engine": {"score": 10}}
    with patch.object(
        signa_service._default_client,
        "get_signal",
        new=AsyncMock(return_value=payload),
    ):
        assert await get_signa_signal("AAPL") is None


async def test_get_signa_signal_returns_none_on_empty_ticker():
    assert await get_signa_signal("") is None


async def test_get_signa_signal_returns_none_when_client_returns_none():
    with patch.object(
        signa_service._default_client,
        "get_signal",
        new=AsyncMock(return_value=None),
    ):
        assert await get_signa_signal("AAPL") is None


# ---------------------------------------------------------------------------
# get_signa_live_feed normalization
# ---------------------------------------------------------------------------


def _real_feed_payload() -> dict[str, Any]:
    """Mirrors the actual ``/api/signals/feed`` response (abridged)."""
    return {
        "type": "raw",
        "count": 5,
        "date": "2026-06-05",
        "signals": [
            {
                "id": "buy-1",
                "ticker": "mna",
                "signal": "BUY",
                "model_id": "merger-arbitrage",
                "model_name": "MergerArbitrageAgent",
                "model_source": "Mitchell & Pulvino (2001)",
                "category": "fundamental",
                "confidence": 0.78,
                "reason": "Merger arbitrage spread wide.",
                "entry_price": 36.3,
                "stop_level": None,
                "target_price": None,
                "position_size_pct": 0.08,
                "conflict_detected": False,
                "grade": "A",
                "tier": 1,
                "score": 98,
                "created_at": "2026-06-05T04:03:07.287922+00:00",
            },
            {
                "id": "short-1",
                "ticker": "TSLA",
                "signal": "SHORT",
                "model_name": "TrendBreakAgent",
                "category": "technical",
                "confidence": 0.61,
                "reason": "Breakdown below support.",
                "grade": None,
                "tier": None,
                "score": None,
                "created_at": "2026-06-05T05:00:00+00:00",
            },
            # Non-directional -> dropped.
            {"id": "avoid-1", "ticker": "XLE", "signal": "AVOID", "confidence": 0.62},
            {"id": "watch-1", "ticker": "SPY", "signal": "WATCH", "confidence": 0.5},
            {"id": "hold-1", "ticker": "QQQ", "signal": "HOLD", "confidence": 0.55},
        ],
    }


async def test_get_signa_live_feed_keeps_directional_drops_noise():
    with patch.object(
        signa_service._default_client,
        "get_feed",
        new=AsyncMock(return_value=_real_feed_payload()),
    ):
        feed = await get_signa_live_feed()

    # Only BUY + SHORT survive; AVOID/WATCH/HOLD dropped.
    assert [s["symbol"] for s in feed] == ["MNA", "TSLA"]

    buy = feed[0]
    assert buy == {
        "source": "signa",
        "id": "buy-1",
        "symbol": "MNA",
        "signal": "BUY",
        "direction": "BULLISH",
        "model_id": "merger-arbitrage",
        "model_name": "MergerArbitrageAgent",
        "model_source": "Mitchell & Pulvino (2001)",
        "category": "fundamental",
        "confidence": 0.78,
        "reason": "Merger arbitrage spread wide.",
        "entry_price": 36.3,
        "stop_level": None,
        "target_price": None,
        "position_size_pct": 0.08,
        "grade": "A",
        "tier": 1,
        "score": 98.0,
        "conflict_detected": False,
        "created_at": "2026-06-05T04:03:07.287922+00:00",
        "website": "https://app.getsigna.ai/?sym=MNA",
    }

    short = feed[1]
    assert short["signal"] == "SHORT"
    assert short["direction"] == "BEARISH"
    assert short["score"] is None  # missing score tolerated


async def test_get_signa_live_feed_returns_empty_when_client_returns_none():
    with patch.object(
        signa_service._default_client,
        "get_feed",
        new=AsyncMock(return_value=None),
    ):
        assert await get_signa_live_feed() == []


async def test_get_signa_live_feed_handles_malformed_payload():
    payloads: list[Any] = [
        {"signals": "not-a-list"},
        {"signals": [None, 42, {"signal": "BUY"}, {"ticker": "AAPL"}]},
        {},
    ]
    for payload in payloads:
        with patch.object(
            signa_service._default_client,
            "get_feed",
            new=AsyncMock(return_value=payload),
        ):
            assert await get_signa_live_feed() == []


async def test_signa_client_get_feed_hits_feed_endpoint():
    get_mock = MagicMock(side_effect=lambda *a, **k: _resp(200, {"signals": []}))
    client = SignaClient(api_key="test-key")

    with patch("app.services.signa.aiohttp.ClientSession", _session(get_mock)):
        assert await client.get_feed(limit=1500) is not None

    call = get_mock.call_args_list[0]
    assert call.args[0] == "https://app.getsigna.ai/api/signals/feed"
    assert call.kwargs["params"] == {"limit": 1500}
