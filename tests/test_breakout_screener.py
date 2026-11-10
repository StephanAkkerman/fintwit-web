from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.api.main as main
import app.runtime.breakout_screen as worker
import app.services.breakout_screener as screener
from app.infra.repos import BreakoutRepo
from app.services.breakout_screener import (
    breakout_weeks,
    evaluate_breakout,
    parse_candidate,
    pick_candidates,
)

HEADERS = {"X-API-Key": "test-api-key"}

DECLINE = [100 - 0.8 * i for i in range(50)]
# A 40-week floor around 60 that drifts down a touch, as bases do.
BASE = [60.5 - 0.02 * i + (1 if i % 2 else -1) for i in range(40)]
BREAKOUT = [68, 71, 73]
BASE_VOLUME = 1000


def _weekly(closes, volumes=None, start=date(2024, 1, 1)):
    return [
        {
            "t": (start + timedelta(weeks=i)).isoformat(),
            "close": close,
            "volume": volumes[i] if volumes else BASE_VOLUME,
        }
        for i, close in enumerate(closes)
    ]


def _market(weeks, step=0.5):
    return _weekly([400 + step * i for i in range(weeks)])


def _breakout_series(surge=(3500, 2500, 1800), tail=BREAKOUT):
    closes = DECLINE + BASE + list(tail)
    volumes = [BASE_VOLUME] * (len(DECLINE) + len(BASE)) + list(surge)
    volumes += [BASE_VOLUME] * (len(closes) - len(volumes))
    return _weekly(closes, volumes)


def test_base_breakout_on_volume_and_strength_is_a_signal():
    points = _breakout_series()
    result = evaluate_breakout(points, _market(len(points)))

    assert result["signal"] is True
    assert result["failed"] == []
    assert result["stage"] == 2
    assert result["entered_from"] in (1, 3)
    assert result["base_weeks"] >= screener.MIN_BASE_WEEKS
    assert result["volume_ratio"] == 3.5
    assert result["strong_volume"] is True
    assert result["mansfield_rs"] > 0
    assert result["weeks_since_breakout"] <= screener.FRESH_WEEKS
    assert 0 < result["score"] <= 100
    assert result["as_of"] == points[-1]["t"]


def test_quiet_breakout_fails_only_the_volume_check():
    points = _breakout_series(surge=(1100, 1100, 1100))
    result = evaluate_breakout(points, _market(len(points)))

    assert result["signal"] is False
    assert result["failed"] == ["volume"]
    assert result["score"] is None


def test_lagging_the_market_fails_relative_strength():
    points = _breakout_series()
    # The market tripled while the stock went sideways.
    market = _market(len(points), step=12)
    result = evaluate_breakout(points, market)

    assert "relative_strength" in result["failed"]
    assert result["signal"] is False


def test_long_running_advance_is_not_fresh():
    points = _weekly([50 + i for i in range(80)])
    result = evaluate_breakout(points, _market(len(points)))

    assert result["stage"] == 2
    assert result["checks"]["fresh"] is False
    assert result["signal"] is False


def test_extended_breakout_fails_the_extension_check():
    points = _breakout_series(tail=[80, 90, 100])
    result = evaluate_breakout(points, _market(len(points)))

    assert result["price_vs_ma30w_percent"] > screener.MAX_EXTENSION_PCT
    assert "not_extended" in result["failed"]


def test_too_little_history_is_none():
    assert evaluate_breakout(_weekly([10] * 20), _market(20)) is None


def test_end_reads_no_later_bars():
    points = _breakout_series()
    market = _market(len(points))
    last_base_week = len(DECLINE) + len(BASE) - 1

    before = evaluate_breakout(points, market, end=last_base_week)
    assert before["signal"] is False
    assert before == evaluate_breakout(points[: last_base_week + 1], market)
    assert evaluate_breakout(points, market, end=len(points) + 5) is None


def test_breakout_weeks_returns_the_first_week_of_each_run():
    points = _breakout_series(tail=BREAKOUT + [74, 75])
    signals = breakout_weeks(points, _market(len(points)))

    assert len(signals) == 1
    first = signals[0]
    # It fires once stage 2 is confirmed and keeps passing after that week.
    assert first["t"] == points[len(DECLINE) + len(BASE) + 2]["t"]
    assert first["volume_ratio"] == 3.5


def test_parse_candidate_maps_share_classes_and_last_week_volume():
    row = {
        "s": "NYSE:BRK.B",
        "d": ["BRK.B", "Berkshire", 500.0, "Finance", "Insurance", 1e12, 12.5, 0.1]
        + [3000, 1000],
    }
    parsed = parse_candidate(row)

    assert parsed["symbol"] == "BRK-B"
    assert parsed["exchange"] == "NYSE"
    # Monday's week-to-date volume is tiny; last week's 3x counts instead.
    assert parsed["relative_volume_1w"] == 3.0
    assert parse_candidate({"s": "X", "d": [None]}) is None


def test_pick_candidates_mixes_strength_and_volume_without_duplicates():
    rows = [
        {"symbol": f"S{i}", "perf_3m": 100 - i, "relative_volume_1w": i}
        for i in range(10)
    ]
    picked = [r["symbol"] for r in pick_candidates(rows, 4)]

    assert picked == ["S0", "S1", "S9", "S8"]


@pytest.mark.asyncio
async def test_run_screen_splits_breakouts_and_near_misses(monkeypatch):
    signal = _breakout_series()
    quiet = _breakout_series(surge=(1100, 1100, 1100))
    series = {
        "SPY": _market(len(signal)),
        "GOOD": signal,
        "QUIET": quiet,
        "FLAT": _weekly([20] * 60),
    }

    async def candidates(limit=None):
        return [
            {"symbol": s, "name": s, "sector": "Tech"}
            for s in ("GOOD", "QUIET", "FLAT", "NONE")
        ]

    async def price_series(symbol, range_key):
        return series.get(symbol, [])

    monkeypatch.setattr(screener, "fetch_candidates", candidates)
    monkeypatch.setattr(screener, "get_price_series", price_series)

    result = await screener.run_screen()

    assert result["universe"] == 4
    assert result["evaluated"] == 3  # NONE has no bars; FLAT is staged, not 2
    assert [r["symbol"] for r in result["breakouts"]] == ["GOOD"]
    assert [r["symbol"] for r in result["watch"]] == ["QUIET"]
    assert result["breakouts"][0]["sector"] == "Tech"


@pytest.mark.asyncio
async def test_run_screen_needs_the_scanner(monkeypatch):
    async def candidates(limit=None):
        return None

    monkeypatch.setattr(screener, "fetch_candidates", candidates)
    assert await screener.run_screen() is None


@pytest_asyncio.fixture
async def breakout_repo(db_engine):
    return BreakoutRepo(async_sessionmaker(db_engine, expire_on_commit=False))


def _row(symbol, close, *, signal=True, week="2025-09-15", score=50.0):
    return {
        "symbol": symbol,
        "name": f"{symbol} Inc",
        "sector": "Technology",
        "industry": "Software",
        "breakout_week": week,
        "close": close,
        "signal": signal,
        "score": score if signal else None,
        "failed": [] if signal else ["volume"],
        "mansfield_rs": 10.0,
        "volume_ratio": 2.0 if signal else 1.1,
    }


def _screen(breakouts, watch=()):
    return {
        "as_of": "2025-10-06",
        "universe": 200,
        "evaluated": 180,
        "breakouts": list(breakouts),
        "watch": list(watch),
    }


@pytest.mark.asyncio
async def test_repo_keeps_flag_price_and_promotes_watch_rows(breakout_repo):
    assert await breakout_repo.latest() is None

    await breakout_repo.record_run(
        _screen([_row("AAA", 10.0)], [_row("BBB", 20.0, signal=False)])
    )
    latest = await breakout_repo.latest()
    assert latest["run"]["breakouts"] == 1
    assert [r["symbol"] for r in latest["breakouts"]] == ["AAA"]
    assert [r["symbol"] for r in latest["watch"]] == ["BBB"]
    assert latest["watch"][0]["flagged_at"] is None

    # Next run: AAA moved up and BBB now passes every check.
    await breakout_repo.record_run(_screen([_row("AAA", 12.0), _row("BBB", 22.0)]))
    latest = await breakout_repo.latest()
    by_symbol = {r["symbol"]: r for r in latest["breakouts"]}
    assert by_symbol["AAA"]["flag_price"] == 10.0
    assert by_symbol["AAA"]["return_since_flag_pct"] == 20.0
    assert by_symbol["BBB"]["status"] == "breakout"
    assert by_symbol["BBB"]["flag_price"] == 22.0

    # A run that lists nothing leaves the history but an empty screen.
    await breakout_repo.record_run(_screen([]))
    latest = await breakout_repo.latest()
    assert latest["breakouts"] == [] and latest["watch"] == []
    flagged = await breakout_repo.flagged(days=30)
    assert {r["symbol"] for r in flagged} == {"AAA", "BBB"}

    assert await breakout_repo.update_last_close("aaa", 15.0) == 1
    aaa = await breakout_repo.flagged(symbol="AAA")
    assert aaa[0]["return_since_flag_pct"] == 50.0


@pytest.mark.asyncio
async def test_worker_records_and_tracks_dropped_names(breakout_repo, monkeypatch):
    await breakout_repo.record_run(_screen([_row("OLD", 10.0)]))

    async def run_screen():
        return _screen([_row("NEW", 5.0)])

    async def price_series(symbol, range_key):
        return [{"t": "2025-10-06", "close": 11.0}] if symbol == "OLD" else []

    monkeypatch.setattr(worker, "run_screen", run_screen)
    monkeypatch.setattr(worker, "get_price_series", price_series)

    run = await worker.screen_once(breakout_repo)

    assert run["breakouts"] == 1
    old = await breakout_repo.flagged(symbol="OLD")
    assert old[0]["return_since_flag_pct"] == 10.0


@pytest.mark.asyncio
async def test_breakout_endpoints(async_client, breakout_repo, monkeypatch):
    monkeypatch.setattr(main, "BREAKOUT_REPO", breakout_repo)

    empty = (await async_client.get("/api/stocks/breakouts", headers=HEADERS)).json()
    assert empty["run"] is None
    assert empty["criteria"]["min_volume_ratio"] == screener.MIN_VOLUME_RATIO

    await breakout_repo.record_run(_screen([_row("AAA", 10.0)]))
    await breakout_repo.record_run(_screen([_row("AAA", 9.0)]))

    data = (await async_client.get("/api/stocks/breakouts", headers=HEADERS)).json()
    assert data["run"]["as_of"] == "2025-10-06"
    assert data["breakouts"][0]["symbol"] == "AAA"

    history = (
        await async_client.get("/api/stocks/breakouts/history", headers=HEADERS)
    ).json()
    assert history["summary"] == {
        "flagged": 1,
        "with_return": 1,
        "avg_return_pct": -10.0,
        "win_rate_pct": 0.0,
    }
