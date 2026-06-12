import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infra.db import Base, TweetRow
from app.services.mention_aggregator import get_mention_frequency

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def Session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _tweet(id, author, tickers, days_ago, score=0.0, label="NEUTRAL"):
    return TweetRow(
        id=id,
        text="x",
        user_name=author,
        user_screen_name=author,
        user_img="",
        url=f"u{id}",
        media=[],
        tickers=tickers,
        hashtags=[],
        title="",
        media_types=[],
        created_at=_now() - timedelta(days=days_ago),
        sentiment_label=label,
        sentiment_score=score,
        assets=[{"symbol": t, "kind": "EQUITY", "financials": {}} for t in tickers],
        is_options_tweet=False,
    )


async def _insert(Session, rows):
    async with Session() as s:
        async with s.begin():
            for r in rows:
                s.add(r)


def _stat(result, scope, author, ticker):
    if scope == "personal":
        return result["personal"].get(author, {}).get(ticker)
    return result["global"].get(ticker)


# ── Personal signals ─────────────────────────────────────────────────────────


async def test_personal_new_first_mention(Session):
    await _insert(Session, [_tweet(1, "alice", ["NEWCO"], 1)])
    res = await get_mention_frequency(
        Session, [{"author": "alice", "tickers": ["NEWCO"]}]
    )
    stat = _stat(res, "personal", "alice", "NEWCO")
    assert stat["signal"] == "new"
    assert stat["first_ever"] is True
    assert stat["notable"] is True


async def test_personal_resurfacing(Session):
    # One mention long ago (silent through the prior 30-60d window), then back now.
    await _insert(
        Session,
        [
            _tweet(1, "alice", ["OLD"], 120),
            _tweet(2, "alice", ["OLD"], 2),
        ],
    )
    res = await get_mention_frequency(
        Session, [{"author": "alice", "tickers": ["OLD"]}]
    )
    stat = _stat(res, "personal", "alice", "OLD")
    assert stat["signal"] == "resurfacing"
    assert stat["first_ever"] is False
    assert stat["days_since_last"] is not None and stat["days_since_last"] >= 60


async def test_personal_top_rank(Session):
    # Anchor in the prior window so NVDA reads as 'top', not 'new'/'resurfacing'.
    rows = [_tweet(200, "alice", ["NVDA"], 45)]
    rows += [_tweet(i, "alice", ["NVDA"], 1) for i in range(1, 6)]  # 5 in-window
    rows += [_tweet(20, "alice", ["TSLA"], 1)]  # 1 mention
    await _insert(Session, rows)
    res = await get_mention_frequency(
        Session, [{"author": "alice", "tickers": ["NVDA", "TSLA"]}]
    )
    nvda = _stat(res, "personal", "alice", "NVDA")
    tsla = _stat(res, "personal", "alice", "TSLA")
    assert nvda["signal"] == "top"
    assert nvda["rank"] == 1
    assert tsla["signal"] != "top"


async def test_personal_hot_when_not_rank_one(Session):
    # BBB is rank 1 (12), AAA has 10 (>= HOT_PERSONAL=8) but rank 2 -> 'hot'.
    # AAA gets a prior-window anchor so it reads as 'hot', not 'new'.
    rows = [_tweet(300, "bob", ["AAA"], 45)]
    rows += [_tweet(i, "bob", ["AAA"], 1) for i in range(1, 11)]
    rows += [_tweet(100 + i, "bob", ["BBB"], 1) for i in range(1, 13)]
    await _insert(Session, rows)
    res = await get_mention_frequency(
        Session, [{"author": "bob", "tickers": ["AAA", "BBB"]}]
    )
    aaa = _stat(res, "personal", "bob", "AAA")
    assert aaa["signal"] == "hot"
    assert aaa["rank"] == 2


async def test_personal_trend_rising(Session):
    # Establish history so it's not 'new'; prior-window activity so it's not
    # 'resurfacing'; keep it off rank 1 and below the hot threshold.
    rows = [
        _tweet(1, "carol", ["SPY"], 45),  # prior window (30-60d) -> prev_mentions=1
        _tweet(2, "carol", ["SPY"], 5),  # window
        _tweet(3, "carol", ["SPY"], 3),  # window
        _tweet(4, "carol", ["SPY"], 2),  # window  -> mentions=3 vs prev=1 = +200%
    ]
    rows += [_tweet(50 + i, "carol", ["DOM"], 1) for i in range(1, 9)]  # rank 1
    await _insert(Session, rows)
    res = await get_mention_frequency(
        Session, [{"author": "carol", "tickers": ["SPY"]}]
    )
    spy = _stat(res, "personal", "carol", "SPY")
    assert spy["signal"] == "rising"
    assert spy["pct_change"] == pytest.approx(2.0, abs=0.01)


async def test_personal_stance_bullish(Session):
    rows = [
        _tweet(i, "dan", ["BULLISH_CO"], 2, score=0.8, label="BULLISH")
        for i in range(1, 5)
    ]
    await _insert(Session, rows)
    res = await get_mention_frequency(
        Session, [{"author": "dan", "tickers": ["BULLISH_CO"]}]
    )
    stat = _stat(res, "personal", "dan", "BULLISH_CO")
    assert stat["stance"] == "bullish"
    assert stat["stance_flipped"] is False


async def test_personal_stance_flip_is_notable(Session):
    # Prior window bearish (3), active window bullish (3) -> flip, hence notable
    # even though volume is otherwise unremarkable.
    rows = [
        _tweet(i, "eve", ["FLIP"], 45, score=-0.8, label="BEARISH") for i in range(1, 4)
    ]
    rows += [
        _tweet(10 + i, "eve", ["FLIP"], 3, score=0.8, label="BULLISH")
        for i in range(1, 4)
    ]
    await _insert(Session, rows)
    res = await get_mention_frequency(Session, [{"author": "eve", "tickers": ["FLIP"]}])
    stat = _stat(res, "personal", "eve", "FLIP")
    assert stat["stance"] == "bullish"
    assert stat["stance_flipped"] is True
    assert stat["notable"] is True


async def test_personal_scope_is_per_author(Session):
    # bob mentions NVDA a lot; alice mentions it once. Alice's stat must reflect
    # only her own activity (1 mention, 'new'), not bob's.
    rows = [_tweet(i, "bob", ["NVDA"], 1) for i in range(1, 6)]
    rows += [_tweet(50, "alice", ["NVDA"], 1)]
    await _insert(Session, rows)
    res = await get_mention_frequency(
        Session,
        [
            {"author": "alice", "tickers": ["NVDA"]},
            {"author": "bob", "tickers": ["NVDA"]},
        ],
    )
    assert _stat(res, "personal", "alice", "NVDA")["mentions"] == 1
    assert _stat(res, "personal", "bob", "NVDA")["mentions"] == 5


# ── Global scope ──────────────────────────────────────────────────────────────


async def test_global_aggregates_across_authors(Session):
    rows = [
        _tweet(i, f"u{i}", ["GME"], 1) for i in range(1, 8)
    ]  # 7 authors, 7 mentions
    await _insert(Session, rows)
    res = await get_mention_frequency(Session, [{"author": "u1", "tickers": ["GME"]}])
    glob = _stat(res, "global", None, "GME")
    assert glob["mentions"] == 7
    assert glob["rank"] == 1


async def test_empty_request_returns_empty(Session):
    res = await get_mention_frequency(Session, [])
    assert res == {"personal": {}, "global": {}}
