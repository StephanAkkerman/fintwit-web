import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.runtime.backfill_sentiment import backfill_tweet_sentiment
from tests.conftest import SAMPLE_TWEETS


class _FakeSentimentModel:
    async def warmup(self) -> None:
        return None

    async def classify(self, text: str) -> dict[str, str | float] | None:
        if "bull" in text.lower():
            return {"label": "BULLISH", "emoji": "bull", "score": 0.9}
        if "bear" in text.lower():
            return {"label": "BEARISH", "emoji": "bear", "score": 0.9}
        return {"label": "NEUTRAL", "emoji": "duck", "score": 0.6}

    async def classify_parts(
        self, text: str
    ) -> dict[str, dict[str, str | float] | None]:
        if "\n\n>" not in text:
            return {"main": await self.classify(text), "quoted": None}

        main_text, quote_block = text.split("\n\n>", 1)
        quote_text = quote_block.replace(">", "").strip()
        return {
            "main": await self.classify(main_text),
            "quoted": await self.classify(quote_text),
        }


async def _seed_tweets(tweet_repo) -> None:
    await tweet_repo.upsert_many(SAMPLE_TWEETS)


async def _count_labeled(session_factory) -> int:
    from sqlalchemy import select

    from app.infra.db import TweetRow

    async with session_factory() as session:
        return len(
            (
                await session.execute(
                    select(TweetRow.id).where(TweetRow.sentiment_label.is_not(None))
                )
            ).all()
        )


async def _insert_pre_labeled(session_factory, tweet_id: int) -> None:
    from sqlalchemy import update

    from app.infra.db import TweetRow

    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                update(TweetRow)
                .where(TweetRow.id == tweet_id)
                .values(
                    sentiment_label="NEUTRAL",
                    sentiment_emoji="duck",
                    sentiment_score=0.5,
                )
            )


async def _get_label(session_factory, tweet_id: int) -> str | None:
    from sqlalchemy import select

    from app.infra.db import TweetRow

    async with session_factory() as session:
        row = (
            (
                await session.execute(
                    select(TweetRow.sentiment_label).where(TweetRow.id == tweet_id)
                )
            )
            .scalars()
            .first()
        )
    return row


async def _get_quote_label(session_factory, tweet_id: int) -> str | None:
    from sqlalchemy import select

    from app.infra.db import TweetRow

    async with session_factory() as session:
        row = (
            (
                await session.execute(
                    select(TweetRow.quoted_sentiment_label).where(
                        TweetRow.id == tweet_id
                    )
                )
            )
            .scalars()
            .first()
        )
    return row


@pytest.mark.asyncio
async def test_backfill_updates_missing_sentiment_only(db_engine, tweet_repo):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_tweets(tweet_repo)
    await _insert_pre_labeled(session_factory, SAMPLE_TWEETS[0]["id"])

    stats = await backfill_tweet_sentiment(
        session_factory=session_factory,
        sentiment_model=_FakeSentimentModel(),
        batch_size=2,
        include_existing=False,
    )

    assert stats.scanned == 2
    assert stats.classified == 2
    assert stats.updated == 2
    assert await _count_labeled(session_factory) == 3


@pytest.mark.asyncio
async def test_backfill_dry_run_does_not_persist(db_engine, tweet_repo):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_tweets(tweet_repo)

    stats = await backfill_tweet_sentiment(
        session_factory=session_factory,
        sentiment_model=_FakeSentimentModel(),
        batch_size=5,
        dry_run=True,
    )

    assert stats.classified == len(SAMPLE_TWEETS)
    assert stats.updated == 0
    assert await _count_labeled(session_factory) == 0


@pytest.mark.asyncio
async def test_backfill_include_existing_recomputes_labels(db_engine, tweet_repo):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    await _seed_tweets(tweet_repo)
    await _insert_pre_labeled(session_factory, SAMPLE_TWEETS[0]["id"])

    stats = await backfill_tweet_sentiment(
        session_factory=session_factory,
        sentiment_model=_FakeSentimentModel(),
        include_existing=True,
    )

    assert stats.scanned == len(SAMPLE_TWEETS)
    assert stats.updated == len(SAMPLE_TWEETS)
    assert await _get_label(session_factory, SAMPLE_TWEETS[0]["id"]) == "BULLISH"


@pytest.mark.asyncio
async def test_backfill_writes_quoted_sentiment_separately(db_engine, tweet_repo):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    quote_tweet = {
        **SAMPLE_TWEETS[0],
        "id": 999999,
        "text": "$AAPL Bull update\n\n> Bearish old post",
    }
    await tweet_repo.upsert_many([quote_tweet])

    stats = await backfill_tweet_sentiment(
        session_factory=session_factory,
        sentiment_model=_FakeSentimentModel(),
    )

    assert stats.updated == 1
    assert await _get_label(session_factory, quote_tweet["id"]) == "BULLISH"
    assert await _get_quote_label(session_factory, quote_tweet["id"]) == "BEARISH"
