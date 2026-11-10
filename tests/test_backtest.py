import asyncio
from datetime import date, timedelta

import pytest

from app.services import backtest as bt
from app.services.backtest import (
    BENCHMARK,
    EntryRules,
    ExitRules,
    HitRates,
    Series,
    Signal,
    build_report,
    candidates_for,
    dedupe,
    run_trade,
)

NO_EXITS = ExitRules(**bt.NO_EXITS)


def business_days(start: date, count: int) -> list[date]:
    days, day = [], start
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def make_series(symbol: str, closes: list[float], start=date(2024, 1, 1)) -> Series:
    days = business_days(start, len(closes))
    return Series(
        symbol, [{"t": d.isoformat(), "close": c} for d, c in zip(days, closes)]
    )


def ramp(start: float, end: float, n: int) -> list[float]:
    return [start + (end - start) * i / (n - 1) for i in range(n)]


def test_series_moving_average_and_lookups():
    s = make_series("X", [float(i) for i in range(1, 11)])
    assert s.sma(5, 4) == pytest.approx(3.0)
    assert s.sma(5, 3) is None
    assert s.index_after(s.days[2]) == 3
    assert s.index_after(s.days[-1]) is None
    assert s.close_on_or_before(s.days[0] - timedelta(days=1)) is None


def test_rule6_needs_the_loss_and_a_broken_trend():
    # Flat for a year, then a 40% drop: below cost by 35%+ and below the
    # 200-day average, so rule 6 sells.
    closes = [100.0] * 250 + ramp(100, 60, 20)
    s = make_series("X", closes)
    path = run_trade(s, 249, ExitRules(stage4=False, trail_arm_pct=None))
    assert path.final_reason == "rule6_stop"
    assert path.return_pct == pytest.approx(
        (s.closes[path.fills[0].index] / 100 - 1) * 100
    )
    assert path.return_pct <= -35


def test_plain_stop_ignores_the_trend():
    closes = [100.0] * 250 + ramp(100, 85, 10)
    s = make_series("X", closes)
    rules = ExitRules(
        **{**bt.NO_EXITS, "stop_loss_pct": 10, "stop_needs_broken_trend": False}
    )
    path = run_trade(s, 249, rules)
    assert path.final_reason == "stop_loss"
    assert -12 < path.return_pct <= -10 + 1e-9


def test_rule7_trims_a_third_then_holds_the_rest_above_the_200_day():
    # Bought at 100, runs to 200 (arms at +50%), falls to 150: 25% off the
    # high trims a third; 150 is still far above the 200-day average.
    closes = [100.0] * 250 + ramp(100, 200, 40) + ramp(200, 150, 10)
    s = make_series("X", closes)
    path = run_trade(s, 249, ExitRules(stage4=False, stop_loss_pct=None))
    assert [f.reason for f in path.fills] == ["rule7_trim"]
    assert path.fills[0].fraction == pytest.approx(1 / 3)
    assert path.final_reason == "open"
    trim_price = path.fills[0].price
    assert path.return_pct == pytest.approx(
        ((trim_price / 3 + 150 * 2 / 3) / 100 - 1) * 100
    )


def test_rule8_sells_on_a_weekly_stage_4():
    closes = ramp(50, 150, 300) + ramp(150, 80, 120)
    s = make_series("X", closes)
    path = run_trade(s, 299, ExitRules(stop_loss_pct=None, trail_arm_pct=None))
    assert path.final_reason == "rule8_stage4"
    assert s.week_end[path.fills[0].index]


def test_no_exits_holds_to_the_end_of_the_data():
    s = make_series("X", ramp(100, 50, 300))
    path = run_trade(s, 0, NO_EXITS)
    assert path.final_reason == "open"
    assert path.return_pct == pytest.approx(-50)


def test_dedupe_keeps_one_signal_per_account_symbol_window():
    d = date(2026, 9, 1)
    signals = [
        Signal("AAA", "a", d, "bullish"),
        Signal("AAA", "a", d + timedelta(days=3), "bullish"),
        Signal("AAA", "b", d + timedelta(days=3), "bullish"),
        Signal("AAA", "a", d + timedelta(days=12), "bullish"),
    ]
    kept = dedupe(signals, days=10)
    assert [(s.account, s.day) for s in kept] == [
        ("a", d),
        ("b", d + timedelta(days=3)),
        ("a", d + timedelta(days=12)),
    ]


def test_hit_rates_only_count_calls_graded_before_the_day():
    s = make_series("X", ramp(100, 130, 60), start=date(2026, 9, 1))
    calls = [
        Signal("X", "a", s.days[0], "bullish", price=100.0),
        Signal("X", "a", s.days[10], "bearish", price=s.closes[10]),
    ]
    rates = HitRates(calls, {"X": s})
    assert rates.as_of("a", s.days[0]) == (0, None)
    n, rate = rates.as_of("a", s.days[0] + timedelta(days=8))
    assert (n, rate) == (1, 1.0)
    n, rate = rates.as_of("a", s.days[-1])
    assert (n, rate) == (2, 0.5)


def test_consensus_needs_enough_distinct_accounts():
    s = make_series("X", [100.0] * 30, start=date(2026, 9, 1))
    calls = [
        Signal("X", "a", s.days[1], "bullish"),
        Signal("X", "b", s.days[2], "bullish"),
        Signal("X", "c", s.days[3], "bullish"),
        Signal("X", "d", s.days[4], "bullish"),
    ]
    rules = EntryRules(accounts="all", min_accounts=3)
    found = candidates_for(
        rules, calls, {"X": s}, set(), HitRates([], {}), s.days[0], s.days[-1]
    )
    cands = [c for day in found.values() for c in day]
    assert len(cands) == 1
    assert cands[0].day == s.days[4]
    assert cands[0].accounts == ("a", "b", "c")


def _report_inputs():
    start = date(2025, 1, 1)
    n = 320
    spy = make_series(BENCHMARK, ramp(400, 440, n), start)
    up = make_series("UP", ramp(50, 100, n), start)
    down = make_series("DOWN", ramp(100, 90, 260) + ramp(90, 40, n - 260), start)
    series = {BENCHMARK: spy, "UP": up, "DOWN": down}
    call_day = up.days[260]
    signals = [
        Signal("UP", "Followed", call_day, "bullish", price=up.closes[260]),
        Signal("DOWN", "stranger", call_day, "bullish", price=down.closes[260]),
        Signal("SPY", "Followed", call_day, "bullish", price=spy.closes[260]),
    ]
    return signals, series


def test_report_follows_only_the_followed_accounts_in_the_current_rules():
    signals, series = _report_inputs()
    report = build_report(signals, series, ["followed"])
    current = next(v for v in report["variants"] if v["key"] == "current")
    assert [t["symbol"] for t in current["trade_log"]] == ["UP"]
    assert current["return_pct"] > 0
    assert current["max_drawdown_pct"] <= 0
    # Index trackers are commentary, never buys.
    assert report["signals"] == 2

    everyone = next(v for v in report["variants"] if v["key"] == "all")
    assert "trade_log" not in everyone
    # DOWN sits below its 200-day average, so the trend filter skips it.
    assert everyone["trades"] == 1 and everyone["skipped"]["trend"] == 1
    unfiltered = next(v for v in report["variants"] if v["key"] == "no_filter")
    assert unfiltered["trades"] == 1  # followed-only: DOWN is a stranger's call

    assert report["window"]["start"] == signals[0].day.isoformat()
    assert report["exit_study"]["rows"]
    assert {r["key"] for r in report["exit_study"]["rows"]} >= {"current", "hold"}
    accounts = {row["account"]: row for row in report["accounts"]}
    assert accounts == {} or all(row["d5"] or row["d20"] for row in accounts.values())


def test_report_without_prices_is_empty_not_an_error():
    report = build_report([Signal("X", "a", date(2026, 9, 1), "bullish")], {}, ["a"])
    assert report["variants"] == [] and report["window"] is None


def test_runner_runs_in_the_background_and_keeps_the_result(monkeypatch):
    calls = []

    async def fake_run(Session, followed):
        calls.append(followed)
        await asyncio.sleep(0)
        return {"ok": True}

    monkeypatch.setattr(bt, "run_backtest", fake_run)

    async def scenario():
        runner = bt.BacktestRunner()
        assert runner.status()["status"] == "idle"
        runner.ensure(None, ["B", "a"])
        assert runner.status()["status"] == "running"
        await runner._task
        assert runner.status() == {
            "status": "ready",
            "error": None,
            "result": {"ok": True},
        }
        runner.ensure(None, ["a", "b"])  # same list, still fresh: no new run
        assert not runner.running
        runner.ensure(None, ["a"])  # followed list changed
        await runner._task
        return runner

    asyncio.run(scenario())
    assert calls == [("a", "b"), ("a",)]
