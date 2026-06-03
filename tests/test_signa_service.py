from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

import app.services.signa as signa_service
from app.services.signa import SignaClient, get_signa_signal

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
    _assert_call(
        calls[1], url="https://app.getsigna.ai/api/v1/quote/AAPL", params=None
    )
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


async def test_get_signa_signal_normalizes_payload():
    payload = {
        "ok": True,
        "symbol": "AAPL",
        "timeframe": "1D",
        "signa": "Bullish",
        "data": {"score": 74, "trend": "up", "confidence": 0.81},
    }
    with patch.object(
        signa_service._default_client,
        "get_signal",
        new=AsyncMock(return_value=payload),
    ):
        result = await get_signa_signal("aapl")

    assert result == {
        "source": "signa",
        "symbol": "AAPL",
        "signal": "Bullish",
        "score": 74,
        "trend": "up",
        "confidence": 0.81,
        "timeframe": "1D",
        "website": "https://app.getsigna.ai/?sym=AAPL",
    }


async def test_get_signa_signal_tolerates_missing_data_fields():
    payload = {"ok": True, "symbol": "AAPL", "signa": "Neutral"}
    with patch.object(
        signa_service._default_client,
        "get_signal",
        new=AsyncMock(return_value=payload),
    ):
        result = await get_signa_signal("AAPL")

    assert result is not None
    assert result["signal"] == "Neutral"
    assert result["score"] is None
    assert result["confidence"] is None
    assert result["trend"] is None


async def test_get_signa_signal_returns_none_without_label():
    payload = {"ok": True, "symbol": "AAPL", "data": {"score": 10}}
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
