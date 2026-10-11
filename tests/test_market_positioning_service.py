from unittest.mock import AsyncMock, patch

import pytest

import app.services.market_positioning_service as svc
from app.services.market_positioning_service import (
    compute_concentration,
    compute_cta_triggers,
    get_market_positioning,
    summarize_futures_positioning,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    svc._reset_cache_for_tests()
    yield
    svc._reset_cache_for_tests()


def _cot_row(date, lev_long, lev_short, code="13874A", oi=1_000_000):
    return {
        "report_date_as_yyyy_mm_dd": f"{date}T00:00:00.000",
        "cftc_contract_market_code": code,
        "open_interest_all": str(oi),
        "lev_money_positions_long": str(lev_long),
        "lev_money_positions_short": str(lev_short),
        "asset_mgr_positions_long": "600000",
        "asset_mgr_positions_short": "100000",
    }


def _points(closes, start_day=1):
    return [
        {"t": f"2026-{1 + (i // 28):02d}-{1 + (i % 28):02d}", "close": c}
        for i, c in enumerate(closes, start=start_day - 1)
    ]


class TestSummarizeFuturesPositioning:
    def test_latest_week_net_change_and_percentile(self):
        rows = [
            _cot_row("2026-09-22", 200_000, 300_000),  # -10%
            _cot_row("2026-09-29", 250_000, 300_000),  # -5%
            _cot_row("2026-10-06", 100_000, 400_000),  # -30%, lowest
        ]

        [es] = summarize_futures_positioning(rows)

        assert es["name"] == "E-mini S&P 500"
        assert es["report_date"] == "2026-10-06"
        assert es["lev_net"] == -300_000
        assert es["lev_net_pct_oi"] == -30.0
        assert es["lev_net_change"] == -250_000
        assert es["lev_percentile"] == pytest.approx(33.3)
        assert es["asset_mgr_net_pct_oi"] == 50.0
        assert [h["date"] for h in es["history"]] == [
            "2026-09-22",
            "2026-09-29",
            "2026-10-06",
        ]

    def test_flags_crowded_short_when_net_is_at_the_bottom_of_its_range(self):
        rows = [
            _cot_row(f"2026-{m:02d}-01", 300_000, 200_000 + m * 1000)
            for m in range(1, 10)
        ] + [_cot_row("2026-10-06", 100_000, 500_000)]

        [es] = summarize_futures_positioning(rows)

        assert es["lev_percentile"] == 10.0
        assert es["crowding"] == "crowded_short"

    def test_flags_crowded_long_at_the_top(self):
        rows = [_cot_row(f"2026-{m:02d}-01", 100_000, 300_000) for m in range(1, 10)]
        rows.append(_cot_row("2026-10-06", 400_000, 100_000))

        [es] = summarize_futures_positioning(rows)

        assert es["crowding"] == "crowded_long"

    def test_keeps_contracts_separate_and_skips_unknown_or_bad_rows(self):
        rows = [
            _cot_row("2026-10-06", 100_000, 200_000),
            _cot_row("2026-10-06", 50_000, 20_000, code="209742", oi=300_000),
            _cot_row("2026-10-06", 1, 2, code="999999"),
            {**_cot_row("2026-10-06", 1, 2), "open_interest_all": "0"},
            {**_cot_row("2026-10-06", 1, 2), "lev_money_positions_long": None},
        ]

        contracts = summarize_futures_positioning(rows)

        assert [c["code"] for c in contracts] == ["13874A", "209742"]
        assert contracts[1]["lev_net_pct_oi"] == 10.0
        assert contracts[0]["lev_net_change"] is None


class TestComputeCtaTriggers:
    def test_all_lookbacks_long_in_a_steady_uptrend(self):
        closes = [100.0 + i for i in range(300)]

        cta = compute_cta_triggers("SPY", closes)

        assert cta["exposure"] == "max_long"
        assert cta["score"] == 1.0
        assert [s["lookback"] for s in cta["signals"]] == ["1M", "3M", "6M", "12M"]
        one_month = cta["signals"][0]
        assert one_month["trigger"] == closes[-22]
        assert one_month["distance_pct"] == pytest.approx(
            round(100 * (closes[-1] - closes[-22]) / closes[-22], 2)
        )
        assert cta["nearest_trigger"] == "1M"

    def test_mixed_signals_after_a_pullback(self):
        # Long uptrend, then a sharp month-long drop below the 1M and 3M references.
        closes = [100.0 + i for i in range(230)] + [329.0 - 2 * i for i in range(30)]

        cta = compute_cta_triggers("SPY", closes)

        signals = {s["lookback"]: s["signal"] for s in cta["signals"]}
        assert signals == {"1M": "short", "3M": "short", "6M": "long", "12M": "long"}
        assert cta["exposure"] == "flat"

    def test_drops_lookbacks_longer_than_history(self):
        cta = compute_cta_triggers("SPY", [100.0 - i for i in range(70)])

        assert [s["lookback"] for s in cta["signals"]] == ["1M", "3M"]
        assert cta["exposure"] == "max_short"

    def test_none_without_enough_history(self):
        assert compute_cta_triggers("SPY", [100.0] * 10) is None
        assert compute_cta_triggers("SPY", []) is None


class TestComputeConcentration:
    def test_narrowing_when_cap_weighted_outruns_equal_weight(self):
        cap = _points([100.0 * (1.002**i) for i in range(260)])
        equal = _points([100.0 * (1.0005**i) for i in range(260)])

        result = compute_concentration(cap, equal)

        assert result["trend"] == "narrowing"
        assert result["headline_window"] == "3M"
        three_month = next(w for w in result["windows"] if w["window"] == "3M")
        assert three_month["spread_pp"] < -2
        assert result["ratio_history"][0]["ratio"] == 100.0
        assert result["ratio_history"][-1]["ratio"] < 100.0
        assert result["ratio_history"][-1]["date"] == cap[-1]["t"]

    def test_broadening_and_stable(self):
        cap = _points([100.0] * 100)
        assert (
            compute_concentration(cap, _points([100.0 * 1.001**i for i in range(100)]))[
                "trend"
            ]
            == "broadening"
        )
        assert compute_concentration(cap, _points([100.0] * 100))["trend"] == "stable"

    def test_only_aligns_dates_both_series_share(self):
        assert compute_concentration(_points([100.0] * 5), []) is None


class TestGetMarketPositioning:
    async def test_combines_sections_and_caches(self):
        closes = [100.0 + i for i in range(260)]
        series = AsyncMock(side_effect=lambda symbol, _range: _points(closes))
        cot = AsyncMock(return_value=[_cot_row("2026-10-06", 100_000, 200_000)])

        with (
            patch.object(svc, "_fetch_cot_rows", cot),
            patch.object(svc, "get_price_series", series),
        ):
            first = await get_market_positioning()
            second = await get_market_positioning()

        assert first is second
        assert cot.await_count == 1
        assert first["futures"][0]["code"] == "13874A"
        assert first["cta"]["exposure"] == "max_long"
        assert first["concentration"]["trend"] == "stable"

    async def test_one_failed_source_leaves_the_others(self):
        series = AsyncMock(return_value=_points([100.0 + i for i in range(100)]))

        with (
            patch.object(svc, "_fetch_cot_rows", AsyncMock(return_value=None)),
            patch.object(svc, "get_price_series", series),
        ):
            result = await get_market_positioning()

        assert result["futures"] is None
        assert result["cta"] is not None

    async def test_none_when_everything_failed(self):
        with (
            patch.object(svc, "_fetch_cot_rows", AsyncMock(side_effect=RuntimeError)),
            patch.object(svc, "get_price_series", AsyncMock(return_value=[])),
        ):
            assert await get_market_positioning() is None
