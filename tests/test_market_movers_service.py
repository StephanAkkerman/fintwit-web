"""Tests for market_movers_service."""

import pytest
import app.services.market_movers_service as svc

pytestmark = pytest.mark.asyncio


def _make_mover(symbol: str, change_pct: float) -> dict:
    return {
        "symbol": symbol,
        "name": f"{symbol} Corp",
        "price": 100.0,
        "extended_price": 100.0 + change_pct,
        "change_pct": change_pct,
        "volume": 500_000,
        "market_cap": 5e9,
    }


FAKE_GAINERS = [_make_mover(f"G{i:02d}", float(i + 1)) for i in range(10)]
FAKE_LOSERS = [_make_mover(f"L{i:02d}", float(-(i + 1))) for i in range(10)]


async def test_get_market_movers_shape(monkeypatch):
    monkeypatch.setattr(svc, "_cache", None)

    async def fake_fetch(prefix: str) -> tuple[list, list]:
        return FAKE_GAINERS, FAKE_LOSERS

    monkeypatch.setattr(svc, "_fetch_movers", fake_fetch)

    result = await svc.get_market_movers()

    assert result is not None
    assert result["session_type"] in ("pre-market", "after-hours")
    assert result["stale"] is False
    assert len(result["gainers"]) == 10
    assert len(result["losers"]) == 10
    for key in (
        "symbol",
        "name",
        "price",
        "extended_price",
        "change_pct",
        "volume",
        "market_cap",
    ):
        assert key in result["gainers"][0], f"Missing key in gainer: {key}"
        assert key in result["losers"][0], f"Missing key in loser: {key}"


async def test_get_market_movers_cache(monkeypatch):
    monkeypatch.setattr(svc, "_cache", None)
    call_count = 0

    async def fake_fetch(prefix: str) -> tuple[list, list]:
        nonlocal call_count
        call_count += 1
        return FAKE_GAINERS, FAKE_LOSERS

    monkeypatch.setattr(svc, "_fetch_movers", fake_fetch)

    result1 = await svc.get_market_movers()
    result2 = await svc.get_market_movers()

    assert call_count == 1
    assert result1 is result2


async def test_get_market_movers_returns_none_when_fetch_fails(monkeypatch):
    monkeypatch.setattr(svc, "_cache", None)

    async def fake_fetch_fail(prefix: str) -> tuple[list, list]:
        raise RuntimeError("scanner unavailable")

    monkeypatch.setattr(svc, "_fetch_movers", fake_fetch_fail)

    result = await svc.get_market_movers()

    assert result is None


async def test_get_market_movers_returns_stale_on_failure_with_warm_cache(monkeypatch):
    import time as time_module

    monkeypatch.setattr(svc, "_cache", None)

    async def fake_fetch_success(prefix: str) -> tuple[list, list]:
        return FAKE_GAINERS, FAKE_LOSERS

    monkeypatch.setattr(svc, "_fetch_movers", fake_fetch_success)
    fresh = await svc.get_market_movers()
    assert fresh is not None
    assert fresh["stale"] is False

    # Expire the cache
    current_prefix = svc._current_prefix()
    monkeypatch.setattr(
        svc, "_cache", (time_module.time() - 400, current_prefix, fresh)
    )

    async def fake_fetch_fail(prefix: str) -> tuple[list, list]:
        raise RuntimeError("scanner down")

    monkeypatch.setattr(svc, "_fetch_movers", fake_fetch_fail)

    stale = await svc.get_market_movers()
    assert stale is not None
    assert stale["stale"] is True
    assert stale["gainers"] == fresh["gainers"]
