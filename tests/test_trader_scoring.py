import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infra.db import Base, TraderCallResultRow, TraderCallRow
from app.services.trader_scoring import (
    MIN_CALLS_FOR_BADGE,
    extract_calls,
    find_due_calls,
    get_credibility_batch,
    get_leaderboard,
    get_trader_detail,
    grade_call,
)

pytestmark = pytest.mark.asyncio


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
async def Session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _insert(Session, rows):
    async with Session() as s:
        async with s.begin():
            for r in rows:
                s.add(r)


def _call(
    id,
    ticker="AAPL",
    user="alice",
    direction="bullish",
    price=100.0,
    hours_ago=48,
):
    return TraderCallRow(
        id=id,
        tweet_id=1000 + id,
        ticker=ticker,
        user_screen_name=user,
        direction=direction,
        sentiment_score=0.5 if direction == "bullish" else -0.5,
        asset_kind="EQUITY",
        price_at_call=price,
        called_at=_now() - timedelta(hours=hours_ago),
        created_at=_now() - timedelta(hours=hours_ago),
    )


def _result(call_id, horizon_days, return_pct, correct, price_at_horizon=None):
    return TraderCallResultRow(
        call_id=call_id,
        horizon_days=horizon_days,
        price_at_horizon=price_at_horizon or 100.0 * (1 + return_pct / 100.0),
        return_pct=return_pct,
        correct=correct,
        evaluated_at=_now(),
    )


# ─── extract_calls ─────────────────────────────────────────────────────────


def test_extract_calls_neutral_sentiment_is_skipped():
    tweet = {
        "id": 1,
        "user_screen_name": "alice",
        "created_at": "2026-01-01T00:00:00",
        "sentiment_score": 0.0,
        "tickers": ["AAPL"],
        "assets": [{"symbol": "AAPL", "kind": "EQUITY", "financials": {"price": 1.0}}],
    }
    assert extract_calls(tweet) == []


def test_extract_calls_missing_price_is_skipped():
    tweet = {
        "id": 1,
        "user_screen_name": "alice",
        "created_at": "2026-01-01T00:00:00",
        "sentiment_score": 0.5,
        "tickers": ["AAPL"],
        "assets": [{"symbol": "AAPL", "kind": "EQUITY", "financials": {}}],
    }
    assert extract_calls(tweet) == []


def test_extract_calls_bearish_and_dedup():
    tweet = {
        "id": 7,
        "user_screen_name": "bob",
        "created_at": "2026-01-01T00:00:00",
        "sentiment_score": -0.4,
        "tickers": ["btc", "BTC"],
        "assets": [
            {"symbol": "BTC", "kind": "CRYPTO", "financials": {"price": 50000.0}}
        ],
    }
    calls = extract_calls(tweet)
    assert len(calls) == 1
    call = calls[0]
    assert call["ticker"] == "BTC"
    assert call["direction"] == "bearish"
    assert call["price_at_call"] == 50000.0
    assert call["tweet_id"] == 7
    assert call["user_screen_name"] == "bob"


def test_extract_calls_no_tweet_id_or_author_is_skipped():
    base = {
        "created_at": "2026-01-01T00:00:00",
        "sentiment_score": 0.5,
        "tickers": ["AAPL"],
        "assets": [{"symbol": "AAPL", "kind": "EQUITY", "financials": {"price": 1.0}}],
    }
    assert extract_calls({**base, "user_screen_name": "alice"}) == []  # no id
    assert extract_calls({**base, "id": 1}) == []  # no author


# ─── grade_call ─────────────────────────────────────────────────────────────


def test_grade_call_bullish_correct_when_price_rises():
    graded = grade_call("bullish", 100.0, 110.0)
    assert graded["correct"] is True
    assert graded["return_pct"] == pytest.approx(10.0)


def test_grade_call_bearish_correct_when_price_falls():
    graded = grade_call("bearish", 100.0, 90.0)
    assert graded["correct"] is True
    assert graded["return_pct"] == pytest.approx(-10.0)


def test_grade_call_bullish_wrong_when_price_falls():
    graded = grade_call("bullish", 100.0, 90.0)
    assert graded["correct"] is False


# ─── find_due_calls ──────────────────────────────────────────────────────────


async def test_find_due_calls_excludes_already_graded_and_not_yet_due(Session):
    await _insert(
        Session,
        [
            _call(1, hours_ago=48),  # due at 1d, ungraded
            _call(2, hours_ago=1),  # not due at 1d yet
        ],
    )
    await _insert(Session, [_result(1, horizon_days=1, return_pct=5.0, correct=True)])
    # call 1 is graded at 1d already; add a fresh ungraded call to prove the query works
    await _insert(Session, [_call(3, hours_ago=48)])

    due = await find_due_calls(Session, horizon_days=1)
    due_ids = {d["id"] for d in due}
    assert 1 not in due_ids  # already graded
    assert 2 not in due_ids  # not due yet
    assert 3 in due_ids


# ─── get_leaderboard ─────────────────────────────────────────────────────────


async def test_leaderboard_ranks_by_hit_rate_and_respects_min_calls(Session):
    # alice: 3/3 correct
    await _insert(Session, [_call(i, user="alice") for i in range(1, 4)])
    await _insert(
        Session,
        [_result(i, 7, return_pct=5.0, correct=True) for i in range(1, 4)],
    )
    # bob: 1/2 correct, below default min_calls of 5 so excluded by default
    await _insert(Session, [_call(i, user="bob") for i in range(4, 6)])
    await _insert(
        Session,
        [
            _result(4, 7, return_pct=5.0, correct=True),
            _result(5, 7, return_pct=-5.0, correct=False),
        ],
    )

    board = await get_leaderboard(Session, horizon_days=7, min_calls=3)
    assert len(board) == 1
    assert board[0]["user_screen_name"] == "alice"
    assert board[0]["hit_rate"] == pytest.approx(1.0)
    assert board[0]["graded_calls"] == 3

    board_low_floor = await get_leaderboard(Session, horizon_days=7, min_calls=1)
    names = {row["user_screen_name"] for row in board_low_floor}
    assert names == {"alice", "bob"}


async def test_leaderboard_signs_return_by_direction(Session):
    # A correct bearish call has a negative return_pct but should count as a
    # positive "what you'd have made by following the call" figure.
    await _insert(Session, [_call(1, user="carol", direction="bearish")])
    await _insert(
        Session,
        [_result(1, 7, return_pct=-8.0, correct=True)],
    )

    board = await get_leaderboard(Session, horizon_days=7, min_calls=1)
    assert board[0]["avg_return_pct"] == pytest.approx(8.0)


# ─── get_trader_detail ────────────────────────────────────────────────────────


async def test_trader_detail_reports_all_horizons_and_recent_calls(Session):
    await _insert(Session, [_call(1, user="dave")])
    await _insert(Session, [_result(1, 1, return_pct=2.0, correct=True)])

    detail = await get_trader_detail(Session, "dave")
    assert detail["user_screen_name"] == "dave"

    horizon_map = {h["horizon_days"]: h for h in detail["horizons"]}
    assert horizon_map[1]["graded_calls"] == 1
    assert horizon_map[1]["hit_rate"] == pytest.approx(1.0)
    assert horizon_map[7]["graded_calls"] == 0
    assert horizon_map[7]["hit_rate"] is None

    assert len(detail["recent_calls"]) == 1
    call = detail["recent_calls"][0]
    assert call["ticker"] == "AAPL"
    assert call["results"][0]["horizon_days"] == 1


async def test_trader_detail_is_case_insensitive_on_screen_name(Session):
    await _insert(Session, [_call(1, user="EveTrader")])
    detail = await get_trader_detail(Session, "evetrader")
    assert len(detail["recent_calls"]) == 1


# ─── get_credibility_batch ────────────────────────────────────────────────────


async def test_credibility_batch_omits_traders_below_min_calls(Session):
    assert MIN_CALLS_FOR_BADGE == 3  # documents the threshold this test relies on

    await _insert(Session, [_call(i, user="frank") for i in range(1, 3)])  # 2 calls
    await _insert(
        Session,
        [_result(i, 7, return_pct=5.0, correct=True) for i in range(1, 3)],
    )

    batch = await get_credibility_batch(Session, ["frank"], horizon_days=7)
    assert batch == {}


async def test_credibility_batch_returns_matching_traders_keyed_lowercase(Session):
    await _insert(Session, [_call(i, user="GraceTrader") for i in range(1, 4)])
    await _insert(
        Session,
        [_result(i, 7, return_pct=5.0, correct=True) for i in range(1, 4)],
    )

    batch = await get_credibility_batch(
        Session, ["GraceTrader", "nobody"], horizon_days=7
    )

    assert set(batch.keys()) == {"gracetrader"}
    stat = batch["gracetrader"]
    assert stat["graded_calls"] == 3
    assert stat["hit_rate"] == pytest.approx(1.0)
    assert stat["horizon_days"] == 7


async def test_credibility_batch_empty_names_returns_empty_dict(Session):
    batch = await get_credibility_batch(Session, [], horizon_days=7)
    assert batch == {}

    batch2 = await get_credibility_batch(Session, ["  ", ""], horizon_days=7)
    assert batch2 == {}
