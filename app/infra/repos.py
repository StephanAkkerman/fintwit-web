from typing import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from .db import TweetRow


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
        return [
            {
                "id": r.id,
                "text": r.text,
                "user_name": r.user_name,
                "user_screen_name": r.user_screen_name,
                "user_img": r.user_img,
                "url": r.url,
                "media": r.media,
                "tickers": r.tickers,
                "hashtags": r.hashtags,
                "title": r.title,
                "media_types": r.media_types,
                "assets": r.assets,
            }
            for r in rows
        ]

    async def since_id(self, since: int, limit: int = 200):
        stmt = (
            select(TweetRow)
            .where(TweetRow.id > since)
            .order_by(TweetRow.id.asc())
            .limit(limit)
        )
        async with self.Session() as s:
            rows = (await s.execute(stmt)).scalars().all()
        return [
            {
                "id": r.id,
                "text": r.text,
                "user_name": r.user_name,
                "user_screen_name": r.user_screen_name,
                "user_img": r.user_img,
                "url": r.url,
                "media": r.media,
                "tickers": r.tickers,
                "hashtags": r.hashtags,
                "title": r.title,
                "media_types": r.media_types,
                "assets": r.assets,
            }
            for r in rows
        ]
