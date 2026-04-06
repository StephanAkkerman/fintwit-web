# app/infra/db.py
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, inspect
from sqlalchemy import text as sql_text
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
    replies: Mapped[int] = mapped_column(Integer, nullable=True)
    likes: Mapped[int] = mapped_column(Integer, nullable=True)
    views: Mapped[int] = mapped_column(Integer, nullable=True)
    retweets: Mapped[int] = mapped_column(Integer, nullable=True)
    sentiment_label: Mapped[str] = mapped_column(String, nullable=True, index=True)
    sentiment_emoji: Mapped[str] = mapped_column(String, nullable=True)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=True)
    assets: Mapped[list] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"),
        default=list,
        server_default=sql_text("'[]'"),
    )
    has_chart: Mapped[bool] = mapped_column(
        Boolean,
        nullable=True,
        default=None,
        server_default=sql_text("NULL"),
    )


class PortfolioPositionRow(Base):
    __tablename__ = "portfolio_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    broker: Mapped[str] = mapped_column(String, index=True, default="IBKR")
    symbol: Mapped[str] = mapped_column(String, index=True)
    quantity: Mapped[float] = mapped_column(Float)
    avg_cost: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String, default="USD")
    opened_at: Mapped[DateTime] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=True, index=True)
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=True, index=True)


def create_engine(url: str = "sqlite+aiosqlite:///./data.db") -> AsyncEngine:
    return create_async_engine(url, future=True)


def _add_missing_columns(sync_conn) -> None:
    """Best-effort schema evolution for additive column changes."""
    inspector = inspect(sync_conn)

    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue

        existing = {col["name"] for col in inspector.get_columns(table_name)}
        for col in table.columns:
            if col.name in existing or col.primary_key:
                continue

            # SQLite only supports additive column ALTERs. Use server default when
            # provided; otherwise keep it nullable to avoid migration failures.
            col_type = col.type.compile(dialect=sync_conn.dialect)
            nullable_sql = ""
            if not col.nullable and col.server_default is not None:
                nullable_sql = " NOT NULL"

            default_sql = ""
            if col.server_default is not None:
                arg = col.server_default.arg
                raw = arg.text if hasattr(arg, "text") else str(arg)
                default_sql = f" DEFAULT {raw}"

            sync_conn.exec_driver_sql(
                f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {col_type}{default_sql}{nullable_sql}'
            )


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)
