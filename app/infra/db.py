# app/infra/db.py
from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

Base = declarative_base()


class TweetRow(Base):
    __tablename__ = "tweets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # tweet id
    text: Mapped[str] = mapped_column(String)
    user_name: Mapped[str] = mapped_column(String)
    user_screen_name: Mapped[str] = mapped_column(String, index=True)
    user_img: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String, index=True)
    media: Mapped[list] = mapped_column(JSON().with_variant(SQLITE_JSON, "sqlite"))
    tickers: Mapped[list] = mapped_column(JSON().with_variant(SQLITE_JSON, "sqlite"))
    hashtags: Mapped[list] = mapped_column(JSON().with_variant(SQLITE_JSON, "sqlite"))
    title: Mapped[str] = mapped_column(String)
    media_types: Mapped[list] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite")
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime, index=True, nullable=True)
    assets: Mapped[list] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"), default=[]
    )


def create_engine(url: str = "sqlite+aiosqlite:///./data.db") -> AsyncEngine:
    return create_async_engine(url, future=True)


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
