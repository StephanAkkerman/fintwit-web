import pandas as pd
import pytest

import app.services.world_indices_service as svc

# Thursday 2026-10-15 17:40 UTC: Asia and Europe have closed, CME is trading.
_NOW = pd.Timestamp("2026-10-15T17:40:00Z")


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(svc, "_now_utc", lambda: _NOW)
    svc._reset_cache_for_tests()
    yield
    svc._reset_cache_for_tests()


def _quotes(changes: dict[str, float], session: str = "regular"):
    async def fake_quote(symbol, asset_hint=None, prefer_realtime=True):
        if symbol not in changes:
            return None
        return {
            "price": 100.0,
            "change_percent": changes[symbol],
            "website": f"https://tv/{symbol}",
            "session": session,
        }

    return fake_quote


@pytest.mark.asyncio
async def test_groups_by_region_with_session_state(monkeypatch):
    monkeypatch.setattr(
        svc,
        "get_tradingview_quote",
        _quotes(
            {
                "KRX:KOSPI": -7.5,
                "TWSE:TAIEX": -3.5,
                "TVC:HSI": -1.0,
                "XETR:DAX": 0.4,
                "CME_MINI:NQ1!": -0.6,
            }
        ),
    )

    data = await svc.get_world_indices()

    assert [r["key"] for r in data["regions"]] == ["asia", "europe", "us_futures"]
    asia = data["regions"][0]
    assert [i["symbol"] for i in asia["indices"]] == ["KOSPI", "TAIEX", "HSI"]
    assert asia["avg_change_percent"] == -4.0

    kospi = asia["indices"][0]
    assert kospi["is_open"] is False
    assert kospi["session_date"] == "2026-10-15"
    assert kospi["next_open"].startswith("2026-10-16")
    assert "SK Hynix" in kospi["read_through"]

    nq = data["regions"][2]["indices"][0]
    assert nq["symbol"] == "NQ"
    assert nq["is_open"] is True
    assert nq["session_date"] is None


@pytest.mark.asyncio
async def test_semis_read_through_flags_a_chip_sell_off(monkeypatch):
    monkeypatch.setattr(
        svc,
        "get_tradingview_quote",
        _quotes({"KRX:KOSPI": -7.5, "TWSE:TAIEX": -3.5, "TVC:HSI": 2.0}),
    )

    data = await svc.get_world_indices()

    assert data["semis"] == {
        "avg_change_percent": -5.5,
        "tone": "bearish",
        "symbols": ["KOSPI", "TAIEX"],
    }


@pytest.mark.asyncio
async def test_semis_neutral_on_small_moves(monkeypatch):
    monkeypatch.setattr(
        svc,
        "get_tradingview_quote",
        _quotes({"TVC:NI225": 0.5, "EURONEXT:AEX": -0.2}),
    )

    data = await svc.get_world_indices()

    assert data["semis"]["tone"] == "neutral"


@pytest.mark.asyncio
async def test_returns_none_and_skips_cache_when_every_quote_fails(monkeypatch):
    calls = 0

    async def failing(symbol, asset_hint=None, prefer_realtime=True):
        nonlocal calls
        calls += 1
        raise RuntimeError("tradingview down")

    monkeypatch.setattr(svc, "get_tradingview_quote", failing)
    assert await svc.get_world_indices() is None
    first = calls

    monkeypatch.setattr(svc, "get_tradingview_quote", _quotes({"XETR:DAX": 1.0}))
    data = await svc.get_world_indices()
    assert first == len(svc.WORLD_INDICES)
    assert data["regions"][0]["key"] == "europe"
    assert data["semis"] is None


@pytest.mark.asyncio
async def test_caches_successful_snapshot(monkeypatch):
    calls = 0

    async def counting(symbol, asset_hint=None, prefer_realtime=True):
        nonlocal calls
        calls += 1
        return {"price": 1.0, "change_percent": 0.0}

    monkeypatch.setattr(svc, "get_tradingview_quote", counting)
    await svc.get_world_indices()
    await svc.get_world_indices()

    assert calls == len(svc.WORLD_INDICES)
