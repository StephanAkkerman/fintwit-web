from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.runtime.market_breadth_snapshot import capture_breadth
from app.services import market_breadth_service as svc


def _row(
    symbol="AAA",
    close=100.0,
    change=1.0,
    sma20=95.0,
    sma50=90.0,
    sma200=110.0,
    high_52w=120.0,
    low_52w=80.0,
    high=101.0,
    low=99.0,
    sector="Finance",
):
    return {
        "s": f"NYSE:{symbol}",
        "d": [
            symbol,
            close,
            change,
            sma20,
            sma50,
            sma200,
            high_52w,
            low_52w,
            high,
            low,
            sector,
        ],
    }


def _members(*rows):
    return [svc.parse_member(r) for r in rows]


def test_parse_member_skips_rows_without_a_close():
    assert svc.parse_member(_row(close=None)) is None
    assert svc.parse_member({"s": "NYSE:X", "d": ["X"]}) is None
    member = svc.parse_member(_row(symbol="JPM"))
    assert member["symbol"] == "JPM"
    assert member["sma200"] == 110.0


def test_universe_counts_moving_averages_and_extremes():
    members = _members(
        _row(symbol="UP", change=2.0, high=120.0),  # new 52-week high
        _row(symbol="DOWN", change=-1.0, close=70.0, low=79.0),  # new low
        _row(symbol="FLAT", change=0.0, sma200=None),
        _row(symbol="UP2", change=0.5, close=115.0),
    )
    universe = svc.build_universe(
        "spx", "S&P 500", "AMEX:SPY", members, {"close": 500.0, "change": 0.8}
    )

    assert universe["members"] == 4
    assert (universe["advancers"], universe["decliners"], universe["unchanged"]) == (
        2,
        1,
        1,
    )
    assert universe["new_highs"] == 1
    assert universe["new_lows"] == 1
    # FLAT has no 200-day average, so the share is over the 3 that do.
    assert universe["pct_above_sma200"] == pytest.approx(33.3)
    assert universe["pct_above_sma50"] == 75.0
    assert universe["benchmark"] == {"symbol": "SPY", "price": 500.0, "change_pct": 0.8}
    assert universe["read"]["day"] == "mixed"
    assert universe["read"]["trend"]["key"] == "weak"


@pytest.mark.parametrize(
    ("change", "advancers_pct", "day"),
    [
        (1.0, 70.0, "broad_rally"),
        (1.0, 30.0, "narrow_rally"),
        (-1.0, 20.0, "broad_selloff"),
        (-1.0, 60.0, "resilient"),
        (-1.0, 50.0, "mixed"),
        (0.1, 90.0, "mixed"),
        (None, 90.0, "mixed"),
    ],
)
def test_read_breadth_classifies_the_day(change, advancers_pct, day):
    stats = {
        "advancers_pct": advancers_pct,
        "new_highs": 0,
        "new_lows": 0,
        "pct_above_sma200": 85.0,
    }
    read = svc.read_breadth(stats, change)
    assert read["day"] == day
    assert read["trend"] == {"key": "overbought", "label": "Overbought"}


def test_read_breadth_mentions_lopsided_highs_and_lows():
    stats = {
        "advancers_pct": 50.0,
        "new_highs": 1,
        "new_lows": 9,
        "pct_above_sma200": 10.0,
    }
    read = svc.read_breadth(stats, 0.0)
    assert "New lows outnumber new highs" in read["note"]
    assert read["trend"]["key"] == "washed_out"


def test_sectors_sorted_by_share_above_50_day():
    members = _members(
        _row(symbol="A", sector="Utilities", close=80.0),
        _row(symbol="B", sector="Technology Services", change=-2.0),
        _row(symbol="C", sector="Technology Services", change=4.0),
        _row(symbol="D", sector=None),
    )
    sectors = svc.summarize_sectors(members)
    assert [s["sector"] for s in sectors] == ["Technology Services", "Utilities"]
    assert sectors[0]["avg_change"] == 1.0
    assert sectors[1]["pct_above_sma50"] == 0.0


@pytest.mark.parametrize(
    ("now", "session"),
    [
        # Monday 2026-10-19 before the open belongs to Friday's session.
        (datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc), "2026-10-16"),
        # During Monday's session.
        (datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc), "2026-10-19"),
        # Saturday.
        (datetime(2026, 10, 17, 15, 0, tzinfo=timezone.utc), "2026-10-16"),
        # Monday evening, after the close.
        (datetime(2026, 10, 19, 23, 0, tzinfo=timezone.utc), "2026-10-19"),
    ],
)
def test_session_date_files_reads_under_their_session(now, session):
    assert svc.session_date(now) == session


@pytest.mark.asyncio
async def test_get_market_breadth_builds_every_universe():
    svc._reset_cache_for_tests()
    members = [_row(symbol=f"S{i}", change=1.0 if i % 2 else -1.0) for i in range(6)]
    quotes = [{"s": "AMEX:SPY", "d": ["SPY", 500.0, -0.5]}]

    async def fake_scan(session, payload):
        if "tickers" in payload["symbols"]:
            return quotes
        symbolset = payload["symbols"]["symbolset"][0]
        return [] if symbolset == "SYML:TVC;RUT" else members

    with patch.object(svc, "_scan", side_effect=fake_scan):
        data = await svc.get_market_breadth()

    assert [u["key"] for u in data["universes"]] == ["spx", "ndx"]
    assert data["universes"][0]["benchmark"]["change_pct"] == -0.5
    assert data["universes"][1]["benchmark"]["change_pct"] is None
    assert data["sectors"][0]["members"] == 6
    svc._reset_cache_for_tests()


@pytest.mark.asyncio
async def test_get_market_breadth_none_when_scanner_is_down():
    svc._reset_cache_for_tests()
    with patch.object(svc, "_scan", AsyncMock(return_value=None)):
        assert await svc.get_market_breadth() is None


_BREADTH = {
    "universes": [
        {
            "key": "spx",
            "members": 503,
            "advancers": 300,
            "decliners": 200,
            "new_highs": 20,
            "new_lows": 3,
            "pct_above_sma20": 60.0,
            "pct_above_sma50": 55.0,
            "pct_above_sma200": 65.0,
            "benchmark": {"symbol": "SPY", "price": 500.0, "change_pct": 0.4},
        }
    ],
    "sectors": [],
    "session_date": "2026-10-16",
}


@pytest.mark.asyncio
async def test_capture_breadth_overwrites_the_session_row(market_breadth_repo):
    later = {
        **_BREADTH,
        "universes": [{**_BREADTH["universes"][0], "pct_above_sma200": 66.0}],
    }
    with patch(
        "app.runtime.market_breadth_snapshot.get_market_breadth",
        AsyncMock(side_effect=[_BREADTH, later]),
    ):
        await capture_breadth(market_breadth_repo)
        stored = await capture_breadth(market_breadth_repo)

    assert stored[0]["benchmark_change_pct"] == 0.4
    rows = await market_breadth_repo.list_sessions("spx")
    assert len(rows) == 1
    assert rows[0]["pct_above_sma200"] == 66.0
    assert rows[0]["session_date"] == "2026-10-16"


@pytest.mark.asyncio
async def test_capture_breadth_skips_without_a_session(market_breadth_repo):
    with patch(
        "app.runtime.market_breadth_snapshot.get_market_breadth",
        AsyncMock(return_value={**_BREADTH, "session_date": None}),
    ):
        assert await capture_breadth(market_breadth_repo) == []
    assert await market_breadth_repo.list_sessions("spx") == []
