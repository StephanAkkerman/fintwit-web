# app/infra/repos.py
from typing import Iterable

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from xclient import Tweet

from .db import TweetRow


class TweetRepo:
    """Async repo for tweets."""

    def __init__(self, session_factory: async_sessionmaker):
        self.Session = session_factory

    async def upsert_many(self, tweets: Iterable[Tweet]) -> int:
        n = 0
        async with self.Session() as s:
            async with s.begin():
                for t in tweets:
                    data = t.to_dict()
                    try:
                        await s.execute(insert(TweetRow).values(**data))
                        n += 1
                    except IntegrityError:
                        await s.rollback()
                        await s.begin()
                        await s.execute(
                            update(TweetRow).where(TweetRow.id == t.id).values(**data)
                        )
        return n

    async def latest(self, limit: int = 50):
        stmt = (
            select(TweetRow)
            .order_by(TweetRow.id.desc())  # or created_at.desc() if present
            .limit(limit)
        )
        async with self.Session() as s:
            rows = (await s.execute(stmt)).scalars().all()
        # Convert to dicts that match your frontend type
        out = []
        for r in rows:
            out.append(
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
                }
            )
        return out

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
            }
            for r in rows
        ]
