from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from .db import PortfolioPositionRow, TweetRow, FundingRateRow


def _row_to_dict(r: TweetRow) -> dict:
    return {
        "id": r.id,
        "text": r.text,
        "user_name": r.user_name,
        "user_screen_name": r.user_screen_name,
        "user_img": r.user_img,
        "url": r.url,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "media": r.media,
        "tickers": r.tickers,
        "hashtags": r.hashtags,
        "title": r.title,
        "media_types": r.media_types,
        "replies": r.replies,
        "likes": r.likes,
        "views": r.views,
        "retweets": r.retweets,
        "assets": r.assets,
    }


def _portfolio_row_to_dict(r: PortfolioPositionRow) -> dict:
    return {
        "id": r.id,
        "broker": r.broker,
        "symbol": r.symbol,
        "quantity": float(r.quantity),
        "avg_cost": float(r.avg_cost),
        "currency": r.currency,
        "opened_at": r.opened_at.isoformat() if r.opened_at else None,
        "notes": r.notes,
        "is_active": bool(r.is_active),
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


class TweetRepo:
    """Async repo for tweets."""

    def __init__(self, session_factory: async_sessionmaker):
        self.Session = session_factory

    async def upsert_many(self, tweets: Iterable[dict]) -> int:
        """
        Upsert multiple tweets using a single SQLite ON CONFLICT statement.

        :param tweets: Iterable of dictionaries containing tweet data.
        :return: The total number of tweets processed (inserted or updated).
        """
        tweet_list = list(tweets)
        if not tweet_list:
            return 0

        async with self.Session() as s:
            async with s.begin():
                stmt = sqlite_insert(TweetRow).values(tweet_list)
                # We want to update all columns except the primary key (id) on conflict
                update_cols = {
                    c.name: stmt.excluded[c.name]
                    for c in TweetRow.__table__.c
                    if c.name != "id"
                }
                stmt = stmt.on_conflict_do_update(
                    index_elements=[TweetRow.id],
                    set_=update_cols,
                )
                await s.execute(stmt)
        return len(tweet_list)

    async def latest(self, limit: int = 50):
        stmt = select(TweetRow).order_by(TweetRow.id.desc()).limit(limit)
        async with self.Session() as s:
            rows = (await s.execute(stmt)).scalars().all()
        return [_row_to_dict(r) for r in rows]

    async def by_id(self, tweet_id: int):
        stmt = select(TweetRow).where(TweetRow.id == tweet_id).limit(1)
        async with self.Session() as s:
            row = (await s.execute(stmt)).scalars().first()
        return _row_to_dict(row) if row else None

    async def update_fields(self, tweet_id: int, fields: dict):
        if not fields:
            return await self.by_id(tweet_id)

        async with self.Session() as s:
            async with s.begin():
                await s.execute(
                    update(TweetRow).where(TweetRow.id == tweet_id).values(**fields)
                )

            row = (
                (
                    await s.execute(
                        select(TweetRow).where(TweetRow.id == tweet_id).limit(1)
                    )
                )
                .scalars()
                .first()
            )

        return _row_to_dict(row) if row else None

    async def since_id(self, since: int, limit: int = 200):
        stmt = (
            select(TweetRow)
            .where(TweetRow.id > since)
            .order_by(TweetRow.id.asc())
            .limit(limit)
        )
        async with self.Session() as s:
            rows = (await s.execute(stmt)).scalars().all()
        return [_row_to_dict(r) for r in rows]


class PortfolioRepo:
    """Async repo for portfolio positions."""

    def __init__(self, session_factory: async_sessionmaker):
        self.Session = session_factory

    async def create_position(self, payload: dict) -> dict:
        now = datetime.now(timezone.utc)
        row = PortfolioPositionRow(
            **payload,
            created_at=now,
            updated_at=now,
        )
        async with self.Session() as s:
            async with s.begin():
                s.add(row)
            await s.refresh(row)
        return _portfolio_row_to_dict(row)

    async def list_positions(self, active_only: bool | None = None) -> list[dict]:
        stmt = select(PortfolioPositionRow).order_by(PortfolioPositionRow.id.desc())
        if active_only is not None:
            stmt = stmt.where(PortfolioPositionRow.is_active == active_only)

        async with self.Session() as s:
            rows = (await s.execute(stmt)).scalars().all()
        return [_portfolio_row_to_dict(r) for r in rows]

    async def by_id(self, position_id: int) -> dict | None:
        stmt = (
            select(PortfolioPositionRow)
            .where(PortfolioPositionRow.id == position_id)
            .limit(1)
        )
        async with self.Session() as s:
            row = (await s.execute(stmt)).scalars().first()
        return _portfolio_row_to_dict(row) if row else None

    async def update_position(self, position_id: int, fields: dict) -> dict | None:
        payload = {**fields, "updated_at": datetime.now(timezone.utc)}

        async with self.Session() as s:
            async with s.begin():
                result = await s.execute(
                    update(PortfolioPositionRow)
                    .where(PortfolioPositionRow.id == position_id)
                    .values(**payload)
                )
                if result.rowcount == 0:
                    return None

            row = (
                (
                    await s.execute(
                        select(PortfolioPositionRow)
                        .where(PortfolioPositionRow.id == position_id)
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )

        return _portfolio_row_to_dict(row) if row else None

    async def delete_position(self, position_id: int) -> bool:
        async with self.Session() as s:
            async with s.begin():
                result = await s.execute(
                    delete(PortfolioPositionRow).where(
                        PortfolioPositionRow.id == position_id
                    )
                )
        return bool(result.rowcount)


class FundingRateRepo:
    """Async repo for Binance funding rates."""

    def __init__(self, session_factory: async_sessionmaker):
        self.Session = session_factory

    async def upsert_rates(self, rates: list[dict]) -> None:
        if not rates:
            return

        async with self.Session() as s:
            async with s.begin():
                stmt = sqlite_insert(FundingRateRow).values(rates)

                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol"],
                    set_={
                        "rate": stmt.excluded.rate,
                        "next_funding_time": stmt.excluded.next_funding_time,
                        "updated_at": stmt.excluded.updated_at
                    }
                )
                await s.execute(stmt)

    async def get_lowest_rates(self, limit: int = 15) -> list[dict]:
        stmt = select(FundingRateRow).order_by(FundingRateRow.rate.asc()).limit(limit)
        async with self.Session() as s:
            rows = (await s.execute(stmt)).scalars().all()
            return [
                {
                    "symbol": r.symbol,
                    "lastFundingRate": f"{r.rate:.4f}%",
                    "nextFundingTime": r.next_funding_time.replace(tzinfo=timezone.utc).isoformat() if r.next_funding_time else None,
                    "updated_at": r.updated_at.replace(tzinfo=timezone.utc).isoformat() if r.updated_at else None
                }
                for r in rows
            ]
