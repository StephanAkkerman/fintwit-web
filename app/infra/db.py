# app/infra/db.py
import logging

from sqlalchemy import (
    DDL,
    JSON,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

logger = logging.getLogger(__name__)

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
    # Signed sentiment per ticker, for tweets that say different things about
    # different names ("long $NVDA, short $INTC"). Only holds the tickers whose
    # score differs from `sentiment_score`; everything else reads that.
    ticker_sentiment: Mapped[dict] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"),
        nullable=True,
        default=None,
    )
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
    chart_extraction: Mapped[dict] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"),
        nullable=True,
        default=None,
        server_default=sql_text("NULL"),
    )
    # OCR'd text off a non-chart photo, for tweets whose own text named no
    # ticker (issue #88) — e.g. a screenshot of an options position with no
    # caption. Opt-in via IMAGE_OCR_ENABLED; null when disabled or empty.
    image_text: Mapped[str] = mapped_column(
        String,
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


class TickerMentionRow(Base):
    """One row per (tweet, ticker), mirroring ``tweets.tickers``.

    A search index, not a source of truth: every row is derivable from
    ``tweets`` via ``json_each(tickers)``, database triggers keep it in step
    with every write, and ``_backfill_ticker_mentions`` rebuilds anything
    missing. It exists because ``tickers`` is a JSON blob,
    and no index can reach inside one — answering "when was this ticker last
    mentioned?" from ``tweets`` alone means expanding ``json_each`` over
    every row in the table.

    That made the unbounded history lookups in ``get_hidden_gems`` scale with
    total tweet volume rather than with the question being asked. The
    ``(ticker, created_at)`` index below turns them into per-ticker seeks:
    measured on a 480k-tweet table, the hidden-gems history scan went from
    610ms to 1.3ms, and stopped growing as history accumulates.

    ``created_at`` is denormalised from ``tweets`` so the index alone can
    answer time-ranged questions; anything else a query needs is reached by
    joining back to ``tweets`` on ``tweet_id``, which is that table's primary
    key. Keeping the row this narrow is deliberate — it stays cheap to
    maintain and there is only one copy of the author/sentiment/asset fields.
    """

    __tablename__ = "ticker_mentions"

    tweet_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        # Serves the per-ticker history seeks: `WHERE ticker = ? AND
        # created_at < ?`, plus the MIN/MAX over that range.
        Index("ix_ticker_mentions_ticker_created", "ticker", "created_at"),
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


class TraderCallRow(Base):
    """One directional call: a non-neutral sentiment tweet mentioning a ticker.

    Created once, at enrichment time, from the tweet's already-computed
    sentiment and asset price — no extra fetch needed. Graded later, at one
    or more horizons, by TraderCallResultRow.
    """

    __tablename__ = "trader_calls"
    __table_args__ = (UniqueConstraint("tweet_id", "ticker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tweet_id: Mapped[int] = mapped_column(Integer, index=True)
    ticker: Mapped[str] = mapped_column(String, index=True)
    user_screen_name: Mapped[str] = mapped_column(String, index=True)
    direction: Mapped[str] = mapped_column(String)  # "bullish" | "bearish"
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=True)
    asset_kind: Mapped[str] = mapped_column(String, nullable=True)
    price_at_call: Mapped[float] = mapped_column(Float)
    called_at: Mapped[DateTime] = mapped_column(DateTime, index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime)


class TraderCallResultRow(Base):
    """Grading of one TraderCallRow at one fixed horizon (1d/7d/30d)."""

    __tablename__ = "trader_call_results"
    __table_args__ = (UniqueConstraint("call_id", "horizon_days"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[int] = mapped_column(Integer, index=True)
    horizon_days: Mapped[int] = mapped_column(Integer, index=True)
    price_at_horizon: Mapped[float] = mapped_column(Float)
    return_pct: Mapped[float] = mapped_column(Float)
    correct: Mapped[bool] = mapped_column(Boolean)
    evaluated_at: Mapped[DateTime] = mapped_column(DateTime)


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


class RedditTrendRunRow(Base):
    """One completed Reddit scrape-and-rank pass (issue #6).

    A trend report is expensive — several subreddits scraped, every post run
    through ticker recognition and sentiment — so it is computed on a worker
    interval and stored, not on request. The run row holds everything that
    describes the pass as a whole; the per-ticker rankings live in
    ``reddit_ticker_trends`` and point back here.

    Keeping runs rather than overwriting one row is what makes a ticker's
    mention history chartable over weeks: a live scrape can only ever see as
    far back as the posts still on the listing pages.
    """

    __tablename__ = "reddit_trend_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    captured_at: Mapped[DateTime] = mapped_column(DateTime, index=True)
    window_hours: Mapped[float] = mapped_column(Float)
    baseline_hours: Mapped[float] = mapped_column(Float)
    subreddits: Mapped[list] = mapped_column(JSON().with_variant(SQLITE_JSON, "sqlite"))
    posts_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    posts_in_window: Mapped[int] = mapped_column(Integer, default=0)
    mood: Mapped[str] = mapped_column(String, nullable=True)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=True)
    sentiment_breakdown: Mapped[dict] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"), nullable=True
    )
    rising: Mapped[list] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"), nullable=True
    )
    fading: Mapped[list] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"), nullable=True
    )
    emerging: Mapped[list] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"), nullable=True
    )
    by_subreddit: Mapped[list] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"), nullable=True
    )
    timeline: Mapped[dict] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"), nullable=True
    )


class RedditTickerTrendRow(Base):
    """One ticker's ranking within a :class:`RedditTrendRunRow`.

    Columns mirror ``reddit_stock_analyzer.TickerTrend`` so the ranked list can
    be served straight back without recomputation. ``(run_id, symbol)`` is
    unique, and ``(symbol, captured_at)`` is indexed for the per-ticker
    history chart — the same shape of question ``ticker_mentions`` answers for
    tweets, so it gets the same treatment.
    """

    __tablename__ = "reddit_ticker_trends"
    __table_args__ = (
        UniqueConstraint("run_id", "symbol"),
        Index("ix_reddit_ticker_trends_symbol_captured", "symbol", "captured_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    # Denormalised from the run so the index above answers time-ranged
    # per-ticker questions without joining back.
    captured_at: Mapped[DateTime] = mapped_column(DateTime, index=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    mentions: Mapped[int] = mapped_column(Integer, default=0)
    previous_mentions: Mapped[int] = mapped_column(Integer, default=0)
    unique_authors: Mapped[int] = mapped_column(Integer, default=0)
    score_sum: Mapped[int] = mapped_column(Integer, default=0)
    comment_sum: Mapped[int] = mapped_column(Integer, default=0)
    engagement: Mapped[int] = mapped_column(Integer, default=0)
    mentions_per_hour: Mapped[float] = mapped_column(Float, default=0.0)
    momentum: Mapped[float] = mapped_column(Float, default=0.0)
    change_ratio: Mapped[float] = mapped_column(Float, nullable=True)
    spike_score: Mapped[float] = mapped_column(Float, default=0.0)
    heat_score: Mapped[float] = mapped_column(Float, default=0.0)
    sentiment: Mapped[str] = mapped_column(String, nullable=True)
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    sentiment_breakdown: Mapped[dict] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"), nullable=True
    )
    is_emerging: Mapped[bool] = mapped_column(Boolean, default=False)
    subreddits: Mapped[dict] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"), nullable=True
    )
    sample_posts: Mapped[list] = mapped_column(
        JSON().with_variant(SQLITE_JSON, "sqlite"), nullable=True
    )


# Keeps `ticker_mentions` in lockstep with `tweets.tickers` from inside the
# database, so no writer can leave the index stale — the ORM, `TweetRepo`'s
# ON CONFLICT upsert, raw SQL and test fixtures all go through these. Doing it
# in the write path instead would mean every present and future writer had to
# remember to; here it is structurally impossible to skip.
#
# SQLite-specific DDL, applied only on SQLite. That is not a new constraint:
# every query reading this index goes through `json_each()` in
# `mention_aggregator`, which is SQLite-only already.
_TICKER_MENTION_TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER IF NOT EXISTS trg_ticker_mentions_insert
    AFTER INSERT ON tweets
    BEGIN
        INSERT OR IGNORE INTO ticker_mentions (tweet_id, ticker, created_at)
            SELECT NEW.id, j.value, NEW.created_at FROM json_each(NEW.tickers) j;
    END
    """,
    # Re-ingestion or a reclassification can revise a tweet's tickers, so the
    # update trigger replaces rather than merges: stale rows would otherwise
    # keep a ticker looking mentioned after it was removed.
    """
    CREATE TRIGGER IF NOT EXISTS trg_ticker_mentions_update
    AFTER UPDATE ON tweets
    BEGIN
        DELETE FROM ticker_mentions WHERE tweet_id = NEW.id;
        INSERT OR IGNORE INTO ticker_mentions (tweet_id, ticker, created_at)
            SELECT NEW.id, j.value, NEW.created_at FROM json_each(NEW.tickers) j;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_ticker_mentions_delete
    AFTER DELETE ON tweets
    BEGIN
        DELETE FROM ticker_mentions WHERE tweet_id = OLD.id;
    END
    """,
)


# Attached to the metadata rather than to a single table so the DDL runs once
# every table exists — the triggers live on `tweets` but write to
# `ticker_mentions`, and `create_all` has no foreign key to order those two by.
# Hooking `create_all` (not just `init_db`) is what keeps the index correct for
# every caller that builds a schema, test fixtures included.
for _trigger_ddl in _TICKER_MENTION_TRIGGERS:
    event.listen(
        Base.metadata,
        "after_create",
        DDL(_trigger_ddl).execute_if(dialect="sqlite"),
    )


def _backfill_ticker_mentions(sync_conn) -> int:
    """Populate ``ticker_mentions`` for tweets the index has no rows for.

    Covers the rows that predate the index; the triggers above handle
    everything written from then on. Idempotent and self-healing, so it also
    repairs an index damaged by a restore or a direct write made with
    triggers disabled.

    On an existing database the first run expands the whole table (~1s per
    500k tweets). After that it matches nothing and costs a few milliseconds,
    which is why the ``tickers`` guard is needed: a tweet with no tickers
    legitimately has no rows here, and without the guard every such tweet
    would look permanently un-backfilled and be re-scanned on every startup.
    """
    if sync_conn.dialect.name != "sqlite":
        return 0

    result = sync_conn.exec_driver_sql(
        """
        INSERT OR IGNORE INTO ticker_mentions (tweet_id, ticker, created_at)
        SELECT t.id, j.value, t.created_at
        FROM tweets t, json_each(t.tickers) j
        WHERE t.tickers IS NOT NULL AND t.tickers != '[]'
          AND NOT EXISTS (
              SELECT 1 FROM ticker_mentions tm WHERE tm.tweet_id = t.id
          )
        """
    )
    return result.rowcount or 0


def _analyze_ticker_mentions(sync_conn) -> None:
    """Refresh the query planner's statistics for ``ticker_mentions``.

    Not cosmetic: without stats for this table SQLite misjudges the
    per-ticker seeks in ``get_hidden_gems`` and picks a plan roughly 9x
    slower (measured on a 480k-tweet database: 52ms against 6ms). A database
    migrated onto this index inherits ``sqlite_stat1`` from before the index
    existed, which is exactly the case that misplans, and a database that
    started empty has no stats at all as it grows.

    Run on every startup rather than only after a backfill, so the estimates
    keep up with a table that is still filling. Scoped to the one table —
    a few hundred milliseconds on a half-million rows, once per process, and
    best-effort: bad statistics are a slower plan, never a broken one, so a
    failure here must not stop the app from booting.
    """
    if sync_conn.dialect.name != "sqlite":
        return
    try:
        sync_conn.exec_driver_sql("ANALYZE ticker_mentions")
    except Exception:  # pragma: no cover - advisory only
        logger.warning("ANALYZE ticker_mentions failed; queries may misplan")


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)
        await conn.run_sync(_backfill_ticker_mentions)
        await conn.run_sync(_analyze_ticker_mentions)
