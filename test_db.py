import asyncio
from sqlalchemy import select
from app.infra.db import create_engine, init_db, TweetRow
from app.infra.repos import TweetRepo
from sqlalchemy.ext.asyncio import async_sessionmaker

async def main():
    ENGINE = create_engine("sqlite+aiosqlite:///:memory:")
    await init_db(ENGINE)
    Session = async_sessionmaker(ENGINE, expire_on_commit=False)
    repo = TweetRepo(Session)

    t_dict = {
        "id": 1,
        "text": "test",
        "user_name": "test",
        "user_screen_name": "test",
        "user_img": "test",
        "url": "test",
        "media": ["url1"],
        "tickers": ["$TEST"],
        "hashtags": ["#TEST"],
        "title": "test",
        "media_types": ["photo"],
        "assets": [],
        "is_chart": True
    }

    await repo.upsert_many([t_dict])
    res = await repo.latest(1)
    print(res)

asyncio.run(main())
