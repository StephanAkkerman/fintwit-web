import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.infra.db import TweetRow
from app.runtime.backfill_sentiment import backfill_tweet_sentiment
from tests.conftest import SAMPLE_TWEETS


class _FakeSentimentModel:
    async def warmup(self) -> None:
        return None

    async def classify(
        self, text: str, tickers: list[str] | None = None
    ) -> dict[str, str | float] | None:
        # Scores are signed by direction, as the real model returns them.
        if "bull" in text.lower():
            return {"label": "BULLISH", "emoji": "bull", "score": 0.9}
        if "bear" in text.lower():
            return {"label": "BEARISH", "emoji": "bear", "score": -0.9}
        return {"label": "NEUTRAL", "emoji": "duck", "score": 0.0}

    async def classify_parts(
        self, text: str, tickers: list[str] | None = None
    ) -> dict[str, dict | None]:
        if "\n\n>" not in text:
            return {
                "main": await self.classify(text),
                "quoted": None,
                "tickers": {},
            }

        main_text, quote_block = text.split("\n\n>", 1)
        quote_text = quote_block.replace(">", "").strip()
        return {
            "main": await self.classify(main_text),
            "quoted": await self.classify(quote_text),
            "tickers": {},
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


class _PerTickerSentimentModel(_FakeSentimentModel):
    """Attributes a bearish score to whichever ticker the tweet shorts."""

    async def classify_parts(
        self, text: str, tickers: list[str] | None = None
    ) -> dict[str, dict | None]:
        parts = await super().classify_parts(text, tickers)
        parts["tickers"] = {t: -0.85 for t in (tickers or []) if t == "INTC"}
        return parts


@pytest.mark.asyncio
async def test_backfill_writes_per_ticker_sentiment(db_engine, tweet_repo):
    # The backfill is how historical rows get the per-ticker scores (and the
    # signed ones), so it has to read `tickers` and write `ticker_sentiment`.
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    tweet = {
        **SAMPLE_TWEETS[0],
        "id": 888888,
        "text": "Bull case for $NVDA. $INTC is the short leg.",
        "tickers": ["NVDA", "INTC"],
    }
    await tweet_repo.upsert_many([tweet])

    stats = await backfill_tweet_sentiment(
        session_factory=session_factory,
        sentiment_model=_PerTickerSentimentModel(),
    )

    assert stats.updated == 1
    async with session_factory() as session:
        stored = await session.get(TweetRow, 888888)
        assert stored.ticker_sentiment == {"INTC": -0.85}
        assert stored.sentiment_label == "BULLISH"
