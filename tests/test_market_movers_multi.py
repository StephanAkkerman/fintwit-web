"""Tests for the multi-market movers helpers in market_movers_service."""

import pytest

import app.services.market_movers_service as svc

pytestmark = pytest.mark.asyncio


def _make_mover(symbol: str, change_pct: float, volume: int = 500_000) -> dict:
    return {
        "symbol": symbol,
        "name": f"{symbol} Corp",
        "price": 10.0,
        "change_pct": change_pct,
        "volume": volume,
        "market_cap": 5e9,
    }


FAKE_MOVERS = [_make_mover(f"T{i:02d}", float(i + 1)) for i in range(5)]


@pytest.fixture(autouse=True)
def _reset_cache():
    svc._reset_multi_cache_for_tests()
    yield
    svc._reset_multi_cache_for_tests()


async def test_get_movers_rejects_unknown_market():
    with pytest.raises(ValueError):
        await svc.get_movers("mars", "gainers")


async def test_get_movers_rejects_unknown_category():
    with pytest.raises(ValueError):
        await svc.get_movers("usa", "biggest_ever")


@pytest.mark.parametrize("market", list(svc.MARKETS))
@pytest.mark.parametrize("category", list(svc.CATEGORIES))
async def test_get_movers_shape_for_every_market_category(
    monkeypatch, market, category
):
    async def fake_fetch(m: str, c: str) -> list[dict]:
        assert m == market
        assert c == category
        return FAKE_MOVERS

    monkeypatch.setattr(svc, "_fetch_movers_list", fake_fetch)

    result = await svc.get_movers(market, category)

    assert result == FAKE_MOVERS
    for key in ("symbol", "name", "price", "change_pct", "volume", "market_cap"):
        assert key in result[0], f"Missing key: {key}"


async def test_get_movers_caches_per_market_category_pair(monkeypatch):
    calls: list[tuple[str, str]] = []

    async def fake_fetch(market: str, category: str) -> list[dict]:
        calls.append((market, category))
        return FAKE_MOVERS

    monkeypatch.setattr(svc, "_fetch_movers_list", fake_fetch)

    await svc.get_movers("usa", "gainers")
    await svc.get_movers("usa", "gainers")
    await svc.get_movers("usa", "losers")
    await svc.get_movers("crypto", "gainers")

    assert calls == [("usa", "gainers"), ("usa", "losers"), ("crypto", "gainers")]


async def test_get_movers_returns_none_when_fetch_fails_and_no_cache(monkeypatch):
    async def fake_fetch_fail(market: str, category: str) -> list[dict]:
        raise RuntimeError("scanner unavailable")

    monkeypatch.setattr(svc, "_fetch_movers_list", fake_fetch_fail)

    result = await svc.get_movers("usa", "gainers")

    assert result is None


async def test_get_movers_falls_back_to_stale_cache_on_failure(monkeypatch):
    import time as time_module

    async def fake_fetch_success(market: str, category: str) -> list[dict]:
        return FAKE_MOVERS

    monkeypatch.setattr(svc, "_fetch_movers_list", fake_fetch_success)
    fresh = await svc.get_movers("usa", "gainers")
    assert fresh == FAKE_MOVERS

    svc._multi_cache[("usa", "gainers")] = (time_module.time() - 400, fresh)

    async def fake_fetch_fail(market: str, category: str) -> list[dict]:
        raise RuntimeError("scanner down")

    monkeypatch.setattr(svc, "_fetch_movers_list", fake_fetch_fail)

    stale = await svc.get_movers("usa", "gainers")
    assert stale == fresh


def test_build_movers_payload_penny_stocks_skips_cap_filter():
    payload = svc._build_movers_payload("usa", "penny_stocks")
    left_fields = [f["left"] for f in payload["filter"]]
    assert "market_cap_basic" not in left_fields
    assert {
        "left": "close",
        "operation": "less",
        "right": svc._PENNY_MAX_PRICE,
    } in payload["filter"]
    assert payload["sort"] == {"sortBy": "volume", "sortOrder": "desc"}


def test_build_movers_payload_losers_sorts_ascending():
    payload = svc._build_movers_payload("uk", "losers")
    assert payload["sort"] == {"sortBy": "change", "sortOrder": "asc"}


def test_build_movers_payload_crypto_uses_market_cap_calc():
    payload = svc._build_movers_payload("crypto", "gainers")
    assert "market_cap_calc" in payload["columns"]
    assert any(f["left"] == "market_cap_calc" for f in payload["filter"])


def test_parse_movers_rows_skips_malformed_entries():
    rows = [
        {"s": "NASDAQ:AAPL", "d": ["AAPL", "Apple Inc.", 190.0, 1.5, 1_000_000, 3e12]},
        {"s": "NASDAQ:BAD", "d": ["BAD"]},  # too few columns
        "not-a-dict",
    ]
    parsed = svc._parse_movers_rows(rows)
    assert len(parsed) == 1
    assert parsed[0]["symbol"] == "AAPL"
    assert parsed[0]["change_pct"] == 1.5
