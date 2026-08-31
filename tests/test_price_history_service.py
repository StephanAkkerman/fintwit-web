"""Tests for the price history service (ATH/ATL and 52-week statistics)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services import price_history_service as svc

pytestmark = pytest.mark.asyncio


def _day(offset_days: int) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=offset_days)).isoformat()


def _chart_payload(rows: list[tuple[str, float, float, float]]) -> dict:
    """Build a Yahoo-shaped chart payload from ``(date, close, high, low)``."""
    timestamps = [
        int(
            datetime.fromisoformat(f"{d}T00:00:00+00:00")
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )
        for d, _, _, _ in rows
    ]
    return {
        "chart": {
            "result": [
                {
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "close": [c for _, c, _, _ in rows],
                                "high": [h for _, _, h, _ in rows],
                                "low": [low for _, _, _, low in rows],
                            }
                        ]
                    },
                }
            ]
        }
    }


@pytest.fixture(autouse=True)
def _clear_cache():
    svc._reset_cache_for_tests()
    yield
    svc._reset_cache_for_tests()


def test_normalize_range_accepts_known_keys_and_falls_back():
    assert svc.normalize_range("1y") == "1Y"
    assert svc.normalize_range(" max ") == "MAX"
    assert svc.normalize_range("nonsense") == svc.DEFAULT_RANGE
    assert svc.normalize_range(None) == svc.DEFAULT_RANGE


def test_parse_chart_drops_null_closes():
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1_700_000_000, 1_700_086_400],
                    "indicators": {
                        "quote": [{"close": [None, 12.0], "high": [None, 13.0]}]
                    },
                }
            ]
        }
    }
    points = svc._parse_chart(payload)

    assert len(points) == 1
    assert points[0]["close"] == 12.0
    # High present, low missing -> falls back to close.
    assert points[0]["high"] == 13.0
    assert points[0]["low"] == 12.0


def test_parse_chart_keeps_full_timestamp_for_intraday():
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1_700_000_000, 1_700_003_600],
                    "indicators": {"quote": [{"close": [10.0, 11.0]}]},
                }
            ]
        }
    }
    points = svc._parse_chart(payload, intraday=True)

    assert len(points) == 2
    assert points[0]["t"] != points[1]["t"]
    assert "T" in points[0]["t"]


async def test_get_symbol_stats_flags_asset_at_all_time_high(monkeypatch):
    rows = [
        (_day(400), 50.0, 52.0, 49.0),
        (_day(200), 80.0, 81.0, 78.0),
        (_day(1), 100.0, 100.0, 99.0),
    ]

    async def fake_fetch(symbol, range_, interval):
        return svc._parse_chart(_chart_payload(rows))

    monkeypatch.setattr(svc, "_fetch_chart", fake_fetch)

    stats = await svc.get_symbol_stats("AAPL", price=100.0)

    assert stats["all_time_high"]["value"] == 100.0
    assert stats["all_time_low"]["value"] == 49.0
    assert stats["from_ath_percent"] == pytest.approx(0.0)
    assert stats["from_atl_percent"] == pytest.approx((100 - 49) / 49 * 100)
    assert [f["code"] for f in stats["flags"]] == ["at_ath"]


async def test_get_symbol_stats_flags_near_ath_and_52_week_window(monkeypatch):
    rows = [
        (_day(800), 200.0, 210.0, 190.0),  # all-time high, outside 52w window
        (_day(300), 100.0, 110.0, 95.0),
        (_day(2), 205.0, 206.0, 204.0),
    ]

    async def fake_fetch(symbol, range_, interval):
        return svc._parse_chart(_chart_payload(rows))

    monkeypatch.setattr(svc, "_fetch_chart", fake_fetch)

    stats = await svc.get_symbol_stats("MSFT", price=206.0)

    # 52-week extremes ignore the 800-day-old bar.
    assert stats["week_52_high"]["value"] == 206.0
    assert stats["all_time_high"]["value"] == 210.0
    assert stats["from_ath_percent"] == pytest.approx((206 - 210) / 210 * 100)
    assert [f["code"] for f in stats["flags"]] == ["near_ath"]
    assert stats["range_position_52w"] == pytest.approx(100.0)


async def test_get_symbol_stats_flags_near_all_time_low(monkeypatch):
    rows = [
        (_day(500), 100.0, 105.0, 95.0),
        (_day(100), 40.0, 42.0, 38.0),
        (_day(1), 39.0, 40.0, 38.5),
    ]

    async def fake_fetch(symbol, range_, interval):
        return svc._parse_chart(_chart_payload(rows))

    monkeypatch.setattr(svc, "_fetch_chart", fake_fetch)

    # 1.3% above the 38.0 all-time low -> "near", not "at".
    near = await svc.get_symbol_stats("XYZ", price=38.5)
    assert [f["code"] for f in near["flags"]] == ["near_atl"]
    assert near["all_time_low"]["value"] == 38.0
    assert near["days_since_atl"] is not None

    # Sitting on the low itself flips the flag.
    at_low = await svc.get_symbol_stats("XYZ", price=38.0)
    assert [f["code"] for f in at_low["flags"]] == ["at_atl"]


async def test_get_symbol_stats_reports_recent_extremes(monkeypatch):
    rows = [
        (_day(400), 100.0, 105.0, 90.0),  # all-time low, well in the past
        (_day(20), 300.0, 320.0, 290.0),  # ATH three weeks ago
        (_day(1), 240.0, 245.0, 238.0),  # now well below it
    ]

    async def fake_fetch(symbol, range_, interval):
        return svc._parse_chart(_chart_payload(rows))

    monkeypatch.setattr(svc, "_fetch_chart", fake_fetch)

    stats = await svc.get_symbol_stats("NVDA", price=240.0)

    flags = {f["code"]: f for f in stats["flags"]}
    # Off the ATH but recently there, and sitting at the bottom of the 52w range.
    assert "20d ago" in flags["recent_ath"]["label"]
    assert "near_52w_low" in flags
    assert "at_ath" not in flags and "near_ath" not in flags


async def test_get_symbol_stats_returns_none_without_history(monkeypatch):
    async def fake_fetch(symbol, range_, interval):
        return None

    monkeypatch.setattr(svc, "_fetch_chart", fake_fetch)

    assert await svc.get_symbol_stats("NOPE") is None


async def test_get_price_series_is_cached(monkeypatch):
    calls: list[str] = []

    async def fake_fetch(symbol, range_, interval):
        calls.append(symbol)
        return svc._parse_chart(_chart_payload([(_day(1), 10.0, 11.0, 9.0)]))

    monkeypatch.setattr(svc, "_fetch_chart", fake_fetch)

    first = await svc.get_price_series("AAPL", "1M")
    second = await svc.get_price_series("AAPL", "1M")

    assert first == second
    assert calls == ["AAPL"]


async def test_get_price_series_returns_empty_for_blank_symbol():
    assert await svc.get_price_series("  ") == []


async def test_52_week_flags_suppressed_next_to_an_all_time_extreme(monkeypatch):
    """A holding near its ATH must never also read as near a 52-week low."""
    rows = [
        (_day(700), 50.0, 55.0, 45.0),
        (_day(3), 198.0, 200.0, 196.0),  # the only bar inside the 52w window
    ]

    async def fake_fetch(symbol, range_, interval):
        return svc._parse_chart(_chart_payload(rows))

    monkeypatch.setattr(svc, "_fetch_chart", fake_fetch)

    stats = await svc.get_symbol_stats("AAPL", price=198.0)

    codes = [f["code"] for f in stats["flags"]]
    assert codes == ["near_ath"]
    assert "near_52w_low" not in codes


async def test_52_week_flag_fires_on_a_wide_range_away_from_all_time_extremes(
    monkeypatch,
):
    rows = [
        (_day(2000), 400.0, 420.0, 380.0),  # all-time high, long ago
        (_day(300), 100.0, 105.0, 95.0),  # 52w low
        (_day(2), 199.0, 200.0, 198.0),  # 52w high
    ]

    async def fake_fetch(symbol, range_, interval):
        return svc._parse_chart(_chart_payload(rows))

    monkeypatch.setattr(svc, "_fetch_chart", fake_fetch)

    stats = await svc.get_symbol_stats("WIDE", price=199.0)

    assert [f["code"] for f in stats["flags"]] == ["near_52w_high"]


async def test_flat_instrument_gets_no_extreme_flags(monkeypatch):
    """A price can never read as both at its all-time high and its low."""
    rows = [
        (_day(300), 1000.0, 1002.0, 999.0),
        (_day(2), 1001.0, 1003.0, 1000.0),
    ]

    async def fake_fetch(symbol, range_, interval):
        return svc._parse_chart(_chart_payload(rows))

    monkeypatch.setattr(svc, "_fetch_chart", fake_fetch)

    stats = await svc.get_symbol_stats("FLAT", price=1000.5)

    # 0.4% between the all-time high and low: no proximity claim is meaningful.
    assert stats["flags"] == []
    assert stats["range_position_52w"] is not None


def test_build_flags_reports_only_the_nearer_extreme():
    flags = svc._build_flags(
        from_ath_pct=-1.0,
        from_atl_pct=4.0,
        days_since_ath=1,
        days_since_atl=2,
        from_52w_high_pct=-1.0,
        from_52w_low_pct=4.0,
        all_time_range_pct=20.0,
        range_52w_width_pct=20.0,
    )

    assert [f["code"] for f in flags] == ["near_ath"]
