from typing import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from .db import TweetRow, SPYHeatmapRow


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


def _spy_heatmap_row_to_dict(r: SPYHeatmapRow) -> dict:
    return {
        "ticker": r.ticker,
        "sector": r.sector,
        "industry": r.industry,
        "marketcap": r.marketcap,
        "close": r.close,
        "prev_close": r.prev_close,
        "percentage_change": r.percentage_change,
        "call_volume": r.call_volume,
        "put_volume": r.put_volume,
        "call_premium": r.call_premium,
        "put_premium": r.put_premium,
    }


class SPYHeatmapRepo:
    """Async repo for SPY Heatmap data."""

    def __init__(self, session_factory: async_sessionmaker):
        self.Session = session_factory

    async def upsert_many(self, items: Iterable[dict]) -> int:
        item_list = list(items)
        if not item_list:
            return 0

        async with self.Session() as s:
            async with s.begin():
                stmt = sqlite_insert(SPYHeatmapRow).values(item_list)
                update_cols = {
                    c.name: stmt.excluded[c.name]
                    for c in SPYHeatmapRow.__table__.c
                    if c.name != "ticker"
                }
                stmt = stmt.on_conflict_do_update(
                    index_elements=[SPYHeatmapRow.ticker],
                    set_=update_cols,
                )
                await s.execute(stmt)
        return len(item_list)

    async def latest(self):
        stmt = select(SPYHeatmapRow).order_by(SPYHeatmapRow.marketcap.desc())
        async with self.Session() as s:
            rows = (await s.execute(stmt)).scalars().all()
        return [_spy_heatmap_row_to_dict(r) for r in rows]
