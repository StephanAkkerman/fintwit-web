from typing import Iterable

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from .db import TweetRow


class TweetRepo:
    """Async repo for tweets."""

    def __init__(self, session_factory: async_sessionmaker):
        self.Session = session_factory

    async def upsert_many(self, tweets: Iterable[dict]) -> int:
        # now expects dicts (from tweet.to_dict() plus "assets")
        n = 0
        async with self.Session() as s:
            async with s.begin():
                for d in tweets:
                    # Strip any keys that aren't in TweetRow to avoid insert errors
                    # Note: We must allow 'assets' if it's in TweetRow, which it is.
                    row_keys = {c.name for c in TweetRow.__table__.columns}
                    clean_d = {k: v for k, v in d.items() if k in row_keys}

                    try:
                        await s.execute(insert(TweetRow).values(**clean_d))
                        n += 1
                    except IntegrityError:
                        await s.rollback()
                        await s.begin()
                        await s.execute(
                            update(TweetRow).where(TweetRow.id == clean_d["id"]).values(**clean_d)
                        )
        return n

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
