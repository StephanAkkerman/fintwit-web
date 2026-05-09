import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infra.db import Base, TweetRow

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


def _tweet(id, tickers, label, score, hours_ago, kind="EQUITY", change_pct=0.0):
    return TweetRow(
        id=id, text="x", user_name="u", user_screen_name="u", user_img="",
        url="", media=[], tickers=tickers, hashtags=[], title="",
        media_types=[], created_at=_now() - timedelta(hours=hours_ago),
        sentiment_label=label, sentiment_score=score,
        assets=[{"symbol": t, "kind": kind,
                 "financials": {"change_percent": change_pct}} for t in tickers],
        is_options_tweet=False,
    )


async def _insert(Session, rows):
    async with Session() as s:
        async with s.begin():
            for r in rows:
                s.add(r)


async def test_mention_heat_counts(Session):
    from app.services.mention_aggregator import get_mention_heat

    await _insert(Session, [
        _tweet(1, ["BTC"], "BULL", 0.8, 1, "CRYPTO"),
        _tweet(2, ["BTC"], "BULL", 0.6, 3, "CRYPTO"),
        _tweet(3, ["AAPL"], "BEAR", -0.7, 2, "EQUITY"),
    ])

    rows = await get_mention_heat(Session, min_mentions=1)
    btc = next(r for r in rows if r["ticker"] == "BTC")

    assert btc["mentions_24h"] == 2
    assert btc["asset_kind"] == "CRYPTO"
    assert btc["sentiment_label_24h"] == "BULL"


async def test_mention_heat_avg_sentiment(Session):
    from app.services.mention_aggregator import get_mention_heat

    await _insert(Session, [
        _tweet(1, ["BTC"], "BULL", 0.8, 1, "CRYPTO"),
        _tweet(2, ["BTC"], "BULL", 0.4, 2, "CRYPTO"),
    ])

    rows = await get_mention_heat(Session, min_mentions=1)
    btc = next(r for r in rows if r["ticker"] == "BTC")

    assert abs(btc["avg_sentiment_24h"] - 0.6) < 0.01


async def test_mention_heat_min_mentions_filter(Session):
    from app.services.mention_aggregator import get_mention_heat

    await _insert(Session, [
        _tweet(1, ["BIG"], "BULL", 0.5, 1),
        _tweet(2, ["BIG"], "BULL", 0.5, 2),
        _tweet(3, ["TINY"], "BULL", 0.5, 1),
    ])

    rows = await get_mention_heat(Session, min_mentions=2)
    tickers = [r["ticker"] for r in rows]
    assert "BIG" in tickers
    assert "TINY" not in tickers


async def test_volume_baseline_multiplier(Session):
    from app.services.mention_aggregator import get_volume_baseline

    # 7 tweets today, 1 tweet each in days 1-6 (baseline = 7/7 = 1, multiplier = 7)
    tweets = [_tweet(i, ["GME"], "NEUTRAL", 0.0, i * 0.5) for i in range(1, 8)]
    tweets += [_tweet(i + 10, ["GME"], "NEUTRAL", 0.0, i * 24) for i in range(1, 7)]
    await _insert(Session, tweets)

    rows = await get_volume_baseline(Session, threshold=2.0)
    gme = next((r for r in rows if r["ticker"] == "GME"), None)
    assert gme is not None
    assert gme["volume_multiplier"] > 2.0


async def test_sentiment_shift_detects_swing(Session):
    from app.services.mention_aggregator import get_sentiment_shift

    await _insert(Session, [
        _tweet(1, ["ETH"], "BULL", 0.7, 2),   # current 24h
        _tweet(2, ["ETH"], "BEAR", -0.5, 30),  # prev 24-48h
    ])

    rows = await get_sentiment_shift(Session)
    eth = next((r for r in rows if r["ticker"] == "ETH"), None)
    assert eth is not None
    assert eth["sentiment_label_24h"] == "BULL"
    assert eth["sentiment_label_prev"] == "BEAR"


async def test_hidden_gems_detects_new(Session):
    from app.services.mention_aggregator import get_hidden_gems

    await _insert(Session, [_tweet(1, ["NEWCO"], "BULL", 0.5, 0.5)])

    rows = await get_hidden_gems(Session)
    gem = next((r for r in rows if r["ticker"] == "NEWCO"), None)
    assert gem is not None
    assert gem["gem_subtype"] == "new"


async def test_hidden_gems_detects_resurfacing(Session):
    from app.services.mention_aggregator import get_hidden_gems

    await _insert(Session, [
        _tweet(1, ["OLD"], "BULL", 0.5, 0.5),     # today
        _tweet(2, ["OLD"], "BULL", 0.5, 24 * 10),  # 10 days ago (global history)
    ])

    rows = await get_hidden_gems(Session)
    gem = next((r for r in rows if r["ticker"] == "OLD"), None)
    assert gem is not None
    assert gem["gem_subtype"] == "resurfacing"
    assert gem["days_since_last"] is not None and gem["days_since_last"] >= 9
