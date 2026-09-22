"""Tests for the sector rotation (RRG) service."""

import pytest

from app.services import sector_rotation_service as svc

pytestmark = pytest.mark.asyncio


def _series(closes: list[float], start: str = "2026-01-01") -> list[dict]:
    from datetime import date, timedelta

    start_date = date.fromisoformat(start)
    return [
        {
            "t": (start_date + timedelta(days=i)).isoformat(),
            "close": c,
            "high": c,
            "low": c,
        }
        for i, c in enumerate(closes)
    ]


def test_normalize_timeframe_accepts_known_keys_and_falls_back():
    assert svc.normalize_timeframe("Weekly") == "weekly"
    assert svc.normalize_timeframe("DAILY") == "daily"
    assert svc.normalize_timeframe("nonsense") == svc.DEFAULT_TIMEFRAME
    assert svc.normalize_timeframe(None) == svc.DEFAULT_TIMEFRAME


def test_clamp_tail_bounds_the_requested_length():
    assert svc.clamp_tail(None) == svc.DEFAULT_TAIL
    assert svc.clamp_tail(1) == svc.MIN_TAIL
    assert svc.clamp_tail(100) == svc.MAX_TAIL
    assert svc.clamp_tail(5) == 5


@pytest.mark.parametrize(
    "rs_ratio, rs_momentum, expected",
    [
        (101.0, 101.0, "leading"),
        (101.0, 99.0, "weakening"),
        (99.0, 99.0, "lagging"),
        (99.0, 101.0, "improving"),
        (100.0, 100.0, "leading"),
    ],
)
def test_classify_quadrant(rs_ratio, rs_momentum, expected):
    assert svc.classify_quadrant(rs_ratio, rs_momentum) == expected


def test_compute_rs_ratio_momentum_has_a_warmup_then_valid_values():
    window = 5
    n = 30
    benchmark = [100.0 + i * 0.5 for i in range(n)]
    # Sector steadily outperforms the benchmark.
    sector = [b * 1.001**i for i, b in enumerate(benchmark)]

    rs_ratio, rs_momentum = svc.compute_rs_ratio_momentum(sector, benchmark, window)

    assert len(rs_ratio) == n
    assert len(rs_momentum) == n
    # No values before the rolling window fills.
    assert all(v is None for v in rs_ratio[: window - 1])
    assert rs_ratio[window - 1] is not None
    # Momentum needs a second warmup stage on top of RS-Ratio's own.
    assert rs_momentum[-1] is not None
    assert all(isinstance(v, float) for v in rs_ratio if v is not None)
    assert all(isinstance(v, float) for v in rs_momentum if v is not None)


def test_compute_rs_ratio_momentum_flat_relative_strength_centers_near_100():
    window = 5
    n = 20
    # Sector and benchmark move identically -> RS-Ratio should sit at 100.
    prices = [100.0 + i for i in range(n)]

    rs_ratio, _ = svc.compute_rs_ratio_momentum(prices, prices, window)

    for value in rs_ratio:
        if value is not None:
            assert value == pytest.approx(100.0)


async def test_get_sector_rotation_builds_trails_per_sector(monkeypatch):
    n = 40
    benchmark_series = _series([100.0 + i * 0.3 for i in range(n)])

    async def fake_get_price_series(symbol, range_key):
        if symbol == svc.BENCHMARK:
            return benchmark_series
        if symbol == svc.SECTOR_ETFS["Technology"]:
            return _series([50.0 * 1.01**i for i in range(n)])
        if symbol == svc.SECTOR_ETFS["Energy"]:
            return _series([50.0 * 0.995**i for i in range(n)])
        return []

    monkeypatch.setattr(svc, "get_price_series", fake_get_price_series)

    result = await svc.get_sector_rotation(timeframe="daily", tail=10)

    assert result["benchmark"] == svc.BENCHMARK
    assert result["timeframe"] == "daily"
    sectors_by_name = {s["sector"]: s for s in result["sectors"]}

    # Only sectors with data made it into the response.
    assert set(sectors_by_name) == {"Technology", "Energy"}

    tech = sectors_by_name["Technology"]
    assert tech["etf"] == "XLK"
    assert len(tech["trail"]) == 10
    assert tech["quadrant"] in {"leading", "weakening", "lagging", "improving"}
    for point in tech["trail"]:
        assert set(point) == {"date", "rs_ratio", "rs_momentum"}

    # Outperforming sector reads with a higher RS-Ratio than an underperformer.
    assert (
        tech["trail"][-1]["rs_ratio"]
        > sectors_by_name["Energy"]["trail"][-1]["rs_ratio"]
    )


async def test_get_sector_rotation_returns_empty_sectors_without_benchmark_data(
    monkeypatch,
):
    async def fake_get_price_series(symbol, range_key):
        return []

    monkeypatch.setattr(svc, "get_price_series", fake_get_price_series)

    result = await svc.get_sector_rotation()

    assert result["sectors"] == []


async def test_get_sector_rotation_skips_sector_on_fetch_exception(monkeypatch):
    n = 40
    benchmark_series = _series([100.0 + i * 0.3 for i in range(n)])

    async def fake_get_price_series(symbol, range_key):
        if symbol == svc.BENCHMARK:
            return benchmark_series
        if symbol == svc.SECTOR_ETFS["Technology"]:
            raise RuntimeError("boom")
        if symbol == svc.SECTOR_ETFS["Financials"]:
            return _series([80.0 + i * 0.1 for i in range(n)])
        return []

    monkeypatch.setattr(svc, "get_price_series", fake_get_price_series)

    result = await svc.get_sector_rotation()

    names = {s["sector"] for s in result["sectors"]}
    assert "Technology" not in names
    assert "Financials" in names


async def test_get_sector_rotation_uses_weekly_range_for_weekly_timeframe(monkeypatch):
    seen_ranges: list[str] = []

    async def fake_get_price_series(symbol, range_key):
        seen_ranges.append(range_key)
        return []

    monkeypatch.setattr(svc, "get_price_series", fake_get_price_series)

    await svc.get_sector_rotation(timeframe="weekly")

    assert seen_ranges
    assert all(r == "5Y" for r in seen_ranges)
