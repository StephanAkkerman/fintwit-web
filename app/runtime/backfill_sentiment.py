from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..infra.db import TweetRow, create_engine, init_db
from ..ml.sentiment import FinTwitSentiment


class SentimentModelLike(Protocol):
    async def warmup(self) -> None: ...

    async def classify(self, text: str) -> dict[str, str | float] | None: ...


@dataclass
class BackfillStats:
    scanned: int = 0
    classified: int = 0
    updated: int = 0
    failed: int = 0


async def backfill_tweet_sentiment(
    *,
    session_factory: async_sessionmaker,
    sentiment_model: SentimentModelLike,
    batch_size: int = 64,
    limit: int | None = None,
    include_existing: bool = False,
    dry_run: bool = False,
) -> BackfillStats:
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be > 0 when provided")

    stats = BackfillStats()
    await sentiment_model.warmup()

    last_id = 0
    remaining = limit

    while remaining is None or remaining > 0:
        current_batch_size = min(batch_size, remaining) if remaining else batch_size

        stmt = select(TweetRow.id, TweetRow.text).where(TweetRow.id > last_id)
        if not include_existing:
            stmt = stmt.where(TweetRow.sentiment_label.is_(None))
        stmt = stmt.order_by(TweetRow.id.asc()).limit(current_batch_size)

        async with session_factory() as session:
            rows = (await session.execute(stmt)).all()

        if not rows:
            break

        updates: list[dict] = []
        for tweet_id, text in rows:
            stats.scanned += 1
            last_id = max(last_id, int(tweet_id))

            if not text or not str(text).strip():
                continue

            try:
                sentiment = await sentiment_model.classify(str(text))
            except Exception:
                stats.failed += 1
                continue

            if not sentiment:
                continue

            stats.classified += 1
            updates.append(
                {
                    "tweet_id": int(tweet_id),
                    "sentiment_label": sentiment.get("label"),
                    "sentiment_emoji": sentiment.get("emoji"),
                    "sentiment_score": sentiment.get("score"),
                }
            )

        if not dry_run and updates:
            async with session_factory() as session:
                async with session.begin():
                    for payload in updates:
                        await session.execute(
                            update(TweetRow)
                            .where(TweetRow.id == payload["tweet_id"])
                            .values(
                                sentiment_label=payload["sentiment_label"],
                                sentiment_emoji=payload["sentiment_emoji"],
                                sentiment_score=payload["sentiment_score"],
                            )
                        )
            stats.updated += len(updates)

        if remaining is not None:
            remaining -= len(rows)

    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill tweet sentiment fields using FinTwitBERT"
    )
    parser.add_argument(
        "--db-url",
        default=os.getenv("DB_URL", "sqlite+aiosqlite:///./data.db"),
        help="Database URL used by SQLAlchemy",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="How many tweets to process per batch",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of candidate tweets to scan",
    )
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="Recompute sentiment for tweets that already have sentiment fields",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify and report stats without writing to the database",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    engine = create_engine(args.db_url)
    try:
        await init_db(engine)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        sentiment_model = FinTwitSentiment()

        stats = await backfill_tweet_sentiment(
            session_factory=session_factory,
            sentiment_model=sentiment_model,
            batch_size=args.batch_size,
            limit=args.limit,
            include_existing=args.include_existing,
            dry_run=args.dry_run,
        )

        mode = "DRY RUN" if args.dry_run else "WRITE"
        print(f"[sentiment-backfill] mode={mode}")
        print(f"[sentiment-backfill] scanned={stats.scanned}")
        print(f"[sentiment-backfill] classified={stats.classified}")
        print(f"[sentiment-backfill] updated={stats.updated}")
        print(f"[sentiment-backfill] failed={stats.failed}")
        return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
