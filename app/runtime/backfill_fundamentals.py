from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..infra.db import TweetRow, create_engine, init_db
from ..services.fundamentals_service import get_fundamentals

# Mirrors AssetEnricher._FUNDAMENTALS_KINDS: valuation fundamentals (P/E, EPS,
# NAV, avg volume) only exist for individual companies and funds on Yahoo.
_FUNDAMENTALS_KINDS = {"EQUITY", "ETF"}


class FundamentalsFetcher(Protocol):
    async def __call__(self, symbol: str) -> dict | None: ...


@dataclass
class BackfillStats:
    scanned: int = 0
    candidates: int = 0
    symbols_fetched: int = 0
    updated: int = 0


def _needs_fundamentals(asset: dict, include_existing: bool) -> bool:
    if not isinstance(asset, dict):
        return False
    if str(asset.get("kind") or "").strip().upper() not in _FUNDAMENTALS_KINDS:
        return False
    if include_existing:
        return True
    return not asset.get("fundamentals")


async def backfill_tweet_fundamentals(
    *,
    session_factory: async_sessionmaker,
    fundamentals_fetcher: FundamentalsFetcher = get_fundamentals,
    batch_size: int = 64,
    limit: int | None = None,
    include_existing: bool = False,
    dry_run: bool = False,
) -> BackfillStats:
    """Fill in NAV/P/E/etc. on historical tweets' asset entries.

    These fields were added to the enrichment pipeline after most rows were
    already stored, so they only ever landed on tweets ingested afterward —
    everything older keeps whatever (or nothing) was captured at the time.
    `fundamentals_fetcher` caches per symbol (see `fundamentals_service`), so
    re-running this only re-fetches Yahoo data for symbols not already warm.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be > 0 when provided")

    stats = BackfillStats()
    symbol_cache: dict[str, dict | None] = {}

    last_id = 0
    remaining = limit

    while remaining is None or remaining > 0:
        current_batch_size = min(batch_size, remaining) if remaining else batch_size

        stmt = (
            select(TweetRow.id, TweetRow.assets)
            .where(TweetRow.id > last_id, TweetRow.assets.isnot(None))
            .order_by(TweetRow.id.asc())
            .limit(current_batch_size)
        )
        async with session_factory() as session:
            rows = (await session.execute(stmt)).all()

        if not rows:
            break

        updates: list[dict] = []
        for tweet_id, assets in rows:
            stats.scanned += 1
            last_id = max(last_id, int(tweet_id))

            asset_list = list(assets or [])
            if not any(_needs_fundamentals(a, include_existing) for a in asset_list):
                continue

            stats.candidates += 1
            changed = False
            for asset in asset_list:
                if not _needs_fundamentals(asset, include_existing):
                    continue

                symbol = str(
                    asset.get("yahoo_lookup") or asset.get("symbol") or ""
                ).upper()
                if not symbol:
                    continue

                if symbol not in symbol_cache:
                    symbol_cache[symbol] = await fundamentals_fetcher(symbol)
                    stats.symbols_fetched += 1

                fetched = symbol_cache[symbol]
                if fetched:
                    asset["fundamentals"] = fetched
                    changed = True

            if changed:
                updates.append({"tweet_id": int(tweet_id), "assets": asset_list})

        if not dry_run and updates:
            async with session_factory() as session:
                async with session.begin():
                    for payload in updates:
                        await session.execute(
                            update(TweetRow)
                            .where(TweetRow.id == payload["tweet_id"])
                            .values(assets=payload["assets"])
                        )
            stats.updated += len(updates)
        elif dry_run:
            stats.updated += len(updates)

        if remaining is not None:
            remaining -= len(rows)

    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill NAV/P/E/etc. onto historical tweets' asset entries"
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
        help="Refetch fundamentals for assets that already carry them",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and report stats without writing to the database",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    engine = create_engine(args.db_url)
    try:
        await init_db(engine)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        stats = await backfill_tweet_fundamentals(
            session_factory=session_factory,
            batch_size=args.batch_size,
            limit=args.limit,
            include_existing=args.include_existing,
            dry_run=args.dry_run,
        )

        mode = "DRY RUN" if args.dry_run else "WRITE"
        print(f"[fundamentals-backfill] mode={mode}")
        print(f"[fundamentals-backfill] scanned={stats.scanned}")
        print(f"[fundamentals-backfill] candidates={stats.candidates}")
        print(f"[fundamentals-backfill] symbols_fetched={stats.symbols_fetched}")
        print(f"[fundamentals-backfill] updated={stats.updated}")
        return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
