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
    is_subscriber_only: Mapped[bool] = mapped_column(
        Boolean,
        nullable=True,
        default=None,
        server_default=sql_text("NULL"),
    )
    sentiment_label: Mapped[str] = mapped_column(String, nullable=True, index=True)
    sentiment_emoji: Mapped[str] = mapped_column(String, nullable=True)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=True)
    quoted_sentiment_label: Mapped[str] = mapped_column(
        String, nullable=True, index=True
    )
    quoted_sentiment_emoji: Mapped[str] = mapped_column(String, nullable=True)
    quoted_sentiment_score: Mapped[float] = mapped_column(Float, nullable=True)
    quoted_tweet: Mapped[dict] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"),
        nullable=True,
        default=None,
        server_default=sql_text("NULL"),
    )
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
    is_options_tweet: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sql_text("0"),
        index=True,
    )
    options_context: Mapped[dict] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"),
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


class PortfolioSnapshotRow(Base):
    """Point-in-time record of the portfolio's total value.

    Snapshots are what make the value-over-time chart reflect the portfolio as
    it actually was; the API falls back to reconstructing value from historical
    prices for the period before snapshots existed.
    """

    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String, index=True, default="manual")
    captured_at: Mapped[DateTime] = mapped_column(DateTime, index=True)
    market_value: Mapped[float] = mapped_column(Float)
    cost_basis: Mapped[float] = mapped_column(Float)
    unrealized_pnl: Mapped[float] = mapped_column(Float)
    unrealized_pnl_percent: Mapped[float] = mapped_column(Float)
    positions: Mapped[int] = mapped_column(Integer, default=0)
    breakdown: Mapped[list] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"),
        nullable=True,
        default=None,
        server_default=sql_text("NULL"),
    )


class IbkrPositionRow(Base):
    __tablename__ = "ibkr_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account: Mapped[str] = mapped_column(String, index=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    sec_type: Mapped[str] = mapped_column(String)
    exchange: Mapped[str] = mapped_column(String, nullable=True)
    currency: Mapped[str] = mapped_column(String, default="USD")
    quantity: Mapped[float] = mapped_column(Float)
    avg_cost: Mapped[float] = mapped_column(Float)
    synced_at: Mapped[DateTime] = mapped_column(DateTime, index=True)


class IbkrTradeRow(Base):
    __tablename__ = "ibkr_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exec_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    account: Mapped[str] = mapped_column(String, index=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    sec_type: Mapped[str] = mapped_column(String)
    currency: Mapped[str] = mapped_column(String)
    side: Mapped[str] = mapped_column(String)  # BOT / SLD
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    commission: Mapped[float] = mapped_column(Float, nullable=True)
    executed_at: Mapped[DateTime] = mapped_column(DateTime, index=True, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime)


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
