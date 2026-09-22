import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.infra.db import TweetRow
from app.runtime.backfill_fundamentals import backfill_tweet_fundamentals
from tests.conftest import SAMPLE_TWEETS


class _FakeFetcher:
    """Records calls so tests can assert per-symbol caching behaviour."""

    def __init__(self, responses: dict[str, dict | None]):
        self.responses = responses
        self.calls: list[str] = []

    async def __call__(self, symbol: str) -> dict | None:
        self.calls.append(symbol)
        return self.responses.get(symbol)


async def _seed_tweets(tweet_repo) -> None:
    await tweet_repo.upsert_many(SAMPLE_TWEETS)


async def _get_assets(session_factory, tweet_id: int) -> list:
    async with session_factory() as session:
        row = await session.get(TweetRow, tweet_id)
    return row.assets


@pytest.mark.asyncio
async def test_backfill_fills_missing_fundamentals_only(db_engine, tweet_repo):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_tweets(tweet_repo)
    fetcher = _FakeFetcher({"AAPL": {"forward_pe": 30.0, "market_cap": 3e12}})

    stats = await backfill_tweet_fundamentals(
        session_factory=session_factory,
        fundamentals_fetcher=fetcher,
    )

    assert stats.scanned == len(SAMPLE_TWEETS)
    assert stats.candidates == 1  # only the AAPL tweet qualifies
    assert stats.updated == 1
    assert fetcher.calls == ["AAPL"]

    assets = await _get_assets(session_factory, 1001)
    assert assets[0]["fundamentals"] == {"forward_pe": 30.0, "market_cap": 3e12}


@pytest.mark.asyncio
async def test_backfill_skips_non_equity_etf_kinds(db_engine, tweet_repo):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_tweets(tweet_repo)
    fetcher = _FakeFetcher({"BTC": {"forward_pe": 1.0}})

    await backfill_tweet_fundamentals(
        session_factory=session_factory,
        fundamentals_fetcher=fetcher,
    )

    # BTC (CRYPTO) is never looked up — only the AAPL (EQUITY) tweet is.
    assert fetcher.calls == ["AAPL"]
    assets = await _get_assets(session_factory, 1002)
    assert "fundamentals" not in assets[0]


@pytest.mark.asyncio
async def test_backfill_dry_run_does_not_persist(db_engine, tweet_repo):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_tweets(tweet_repo)
    fetcher = _FakeFetcher({"AAPL": {"forward_pe": 30.0}})

    stats = await backfill_tweet_fundamentals(
        session_factory=session_factory,
        fundamentals_fetcher=fetcher,
        dry_run=True,
    )

    assert stats.updated == 1
    assets = await _get_assets(session_factory, 1001)
    assert "fundamentals" not in assets[0]


@pytest.mark.asyncio
async def test_backfill_include_existing_recomputes(db_engine, tweet_repo):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_tweets(tweet_repo)
    stale_fetcher = _FakeFetcher({"AAPL": {"forward_pe": 10.0}})
    await backfill_tweet_fundamentals(
        session_factory=session_factory, fundamentals_fetcher=stale_fetcher
    )

    fresh_fetcher = _FakeFetcher({"AAPL": {"forward_pe": 42.0}})

    # Without --include-existing, an already-filled asset is left alone.
    await backfill_tweet_fundamentals(
        session_factory=session_factory, fundamentals_fetcher=fresh_fetcher
    )
    assert fresh_fetcher.calls == []
    assets = await _get_assets(session_factory, 1001)
    assert assets[0]["fundamentals"]["forward_pe"] == 10.0

    # With it, the stale value is refetched and overwritten.
    stats = await backfill_tweet_fundamentals(
        session_factory=session_factory,
        fundamentals_fetcher=fresh_fetcher,
        include_existing=True,
    )
    assert stats.updated == 1
    assets = await _get_assets(session_factory, 1001)
    assert assets[0]["fundamentals"]["forward_pe"] == 42.0


@pytest.mark.asyncio
async def test_backfill_fetches_each_symbol_once(db_engine, tweet_repo):
    # Symbol-level caching matters here: many historical tweets repeat the
    # same handful of tickers, and Yahoo shouldn't be hit once per mention.
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    duplicate_tweet = {
        **SAMPLE_TWEETS[0],
        "id": 1004,
        "url": "https://twitter.com/finguru/status/1004",
    }
    await tweet_repo.upsert_many([*SAMPLE_TWEETS, duplicate_tweet])
    fetcher = _FakeFetcher({"AAPL": {"forward_pe": 30.0}})

    stats = await backfill_tweet_fundamentals(
        session_factory=session_factory,
        fundamentals_fetcher=fetcher,
    )

    assert stats.candidates == 2
    assert fetcher.calls == ["AAPL"]
