"""Tests for the `ticker_mentions` search index.

The index mirrors `tweets.tickers`, which is a JSON blob no index can reach
into. `get_hidden_gems` relies on it to answer "has this ticker ever been
mentioned before?" as a per-ticker seek instead of expanding
`json_each(tickers)` across the whole table. That only holds if the index
stays an exact mirror, so these tests pin the maintenance itself: triggers
for live writes, backfill for rows that predate the index.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infra.db import Base, TweetRow, init_db
from app.infra.repos import TweetRepo

pytestmark = pytest.mark.asyncio


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _payload(tweet_id: int, tickers: list[str], hours_ago: float = 1.0) -> dict:
    return {
        "id": tweet_id,
        "text": "x",
        "user_name": "u",
        "user_screen_name": "u",
        "user_img": "",
        "url": f"https://x.com/i/status/{tweet_id}",
        "media": [],
        "tickers": tickers,
        "hashtags": [],
        "title": "",
        "media_types": [],
        "created_at": _now() - timedelta(hours=hours_ago),
        "assets": [],
        "is_options_tweet": False,
    }


async def _index(engine) -> list[tuple]:
    async with engine.connect() as c:
        rows = await c.execute(
            text(
                "SELECT tweet_id, ticker FROM ticker_mentions ORDER BY tweet_id, ticker"
            )
        )
        return [tuple(r) for r in rows.all()]


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    await init_db(eng)
    yield eng
    await eng.dispose()


async def test_upsert_populates_index(engine):
    repo = TweetRepo(async_sessionmaker(engine, expire_on_commit=False))
    await repo.upsert_many([_payload(1, ["AAPL", "BTC"]), _payload(2, ["TSLA"])])

    assert await _index(engine) == [(1, "AAPL"), (1, "BTC"), (2, "TSLA")]


async def test_upsert_replaces_index_when_tickers_change(engine):
    """A re-ingest or reclassification must not leave the old tickers behind.

    Stale rows here would make a ticker look mentioned when it no longer is,
    which for hidden gems means silently dropping a genuine gem.
    """
    repo = TweetRepo(async_sessionmaker(engine, expire_on_commit=False))
    await repo.upsert_many([_payload(1, ["AAPL", "BTC"])])
    await repo.upsert_many([_payload(1, ["NVDA"])])

    assert await _index(engine) == [(1, "NVDA")]


async def test_tweet_with_no_tickers_indexes_nothing(engine):
    repo = TweetRepo(async_sessionmaker(engine, expire_on_commit=False))
    await repo.upsert_many([_payload(1, []), _payload(2, ["SPY"])])

    assert await _index(engine) == [(2, "SPY")]


async def test_repeated_ticker_in_one_tweet_indexes_once(engine):
    """(tweet_id, ticker) is the primary key, and one tweet can repeat a cashtag."""
    repo = TweetRepo(async_sessionmaker(engine, expire_on_commit=False))
    await repo.upsert_many([_payload(1, ["AAPL", "AAPL", "BTC"])])

    assert await _index(engine) == [(1, "AAPL"), (1, "BTC")]


async def test_orm_write_populates_index(engine):
    """Maintenance is in the database, so it covers writers that skip the repo.

    Test fixtures and scripts add rows through the ORM directly; if the index
    were only maintained in `TweetRepo`, those writes would leave it stale.
    """
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        async with s.begin():
            s.add(
                TweetRow(
                    id=7,
                    text="x",
                    user_name="u",
                    user_screen_name="u",
                    user_img="",
                    url="",
                    media=[],
                    tickers=["GME"],
                    hashtags=[],
                    title="",
                    media_types=[],
                    created_at=_now(),
                    assets=[],
                    is_options_tweet=False,
                )
            )

    assert await _index(engine) == [(7, "GME")]


async def test_deleting_a_tweet_clears_its_index_rows(engine):
    repo = TweetRepo(async_sessionmaker(engine, expire_on_commit=False))
    await repo.upsert_many([_payload(1, ["AAPL"]), _payload(2, ["BTC"])])

    async with engine.begin() as c:
        await c.execute(text("DELETE FROM tweets WHERE id = 1"))

    assert await _index(engine) == [(2, "BTC")]


async def test_backfill_indexes_rows_that_predate_the_index(engine):
    """Existing databases have tweets the triggers never saw."""
    repo = TweetRepo(async_sessionmaker(engine, expire_on_commit=False))
    await repo.upsert_many([_payload(1, ["AAPL", "BTC"]), _payload(2, [])])

    # Simulate a database whose tweets were written before the index existed.
    async with engine.begin() as c:
        await c.execute(text("DELETE FROM ticker_mentions"))
    assert await _index(engine) == []

    await init_db(engine)
    assert await _index(engine) == [(1, "AAPL"), (1, "BTC")]


async def test_backfill_is_idempotent(engine):
    repo = TweetRepo(async_sessionmaker(engine, expire_on_commit=False))
    await repo.upsert_many([_payload(1, ["AAPL"])])

    before = await _index(engine)
    await init_db(engine)
    await init_db(engine)

    assert await _index(engine) == before


async def test_index_matches_json_each_expansion(engine):
    """The index must agree with the source of truth it stands in for."""
    repo = TweetRepo(async_sessionmaker(engine, expire_on_commit=False))
    await repo.upsert_many(
        [
            _payload(1, ["AAPL", "BTC"]),
            _payload(2, []),
            _payload(3, ["BTC"]),
            _payload(4, ["ETH", "SOL", "ETH"]),
        ]
    )

    async with engine.connect() as c:
        expected = await c.execute(
            text(
                "SELECT DISTINCT t.id, j.value FROM tweets t, json_each(t.tickers) j"
                " ORDER BY t.id, j.value"
            )
        )
        assert await _index(engine) == [tuple(r) for r in expected.all()]


async def test_create_all_alone_installs_the_triggers():
    """Not every caller runs `init_db`; `create_all` must be enough."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as c:
        await c.run_sync(Base.metadata.create_all)

    repo = TweetRepo(async_sessionmaker(eng, expire_on_commit=False))
    await repo.upsert_many([_payload(1, ["AAPL"])])

    assert await _index(eng) == [(1, "AAPL")]
    await eng.dispose()
