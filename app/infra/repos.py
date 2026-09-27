from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from .db import (
    GammaExposureSnapshotRow,
    IbkrPositionRow,
    IbkrTradeRow,
    PortfolioPositionRow,
    PortfolioSnapshotRow,
    RedditTickerTrendRow,
    RedditTrendRunRow,
    TraderCallResultRow,
    TraderCallRow,
    TweetRow,
)

_TWEET_COLUMNS = {c.name for c in TweetRow.__table__.c}


def _sanitize_tweet_payload(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k in _TWEET_COLUMNS}


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()

    return value.astimezone(timezone.utc).isoformat()


def _row_to_dict(r: TweetRow) -> dict:
    return {
        "id": r.id,
        "text": r.text,
        "user_name": r.user_name,
        "user_screen_name": r.user_screen_name,
        "user_img": r.user_img,
        "url": r.url,
        "created_at": _iso_utc(r.created_at),
        "media": r.media,
        "tickers": r.tickers,
        "hashtags": r.hashtags,
        "title": r.title,
        "media_types": r.media_types,
        "replies": r.replies,
        "likes": r.likes,
        "views": r.views,
        "retweets": r.retweets,
        "is_subscriber_only": r.is_subscriber_only,
        "sentiment_label": r.sentiment_label,
        "sentiment_emoji": r.sentiment_emoji,
        "sentiment_score": r.sentiment_score,
        "quoted_sentiment_label": r.quoted_sentiment_label,
        "quoted_sentiment_emoji": r.quoted_sentiment_emoji,
        "quoted_sentiment_score": r.quoted_sentiment_score,
        "ticker_sentiment": r.ticker_sentiment,
        "quoted_tweet": r.quoted_tweet,
        "has_chart": r.has_chart,
        "chart_extraction": r.chart_extraction,
        "is_options_tweet": r.is_options_tweet,
        "options_context": r.options_context,
        "assets": r.assets,
    }


def _call_row_to_dict(r: TraderCallRow) -> dict:
    return {
        "id": r.id,
        "tweet_id": r.tweet_id,
        "ticker": r.ticker,
        "user_screen_name": r.user_screen_name,
        "direction": r.direction,
        "sentiment_score": r.sentiment_score,
        "asset_kind": r.asset_kind,
        "price_at_call": r.price_at_call,
        "called_at": _iso_utc(r.called_at),
        "created_at": _iso_utc(r.created_at),
    }


def _result_row_to_dict(r: TraderCallResultRow) -> dict:
    return {
        "id": r.id,
        "call_id": r.call_id,
        "horizon_days": r.horizon_days,
        "price_at_horizon": r.price_at_horizon,
        "return_pct": r.return_pct,
        "correct": bool(r.correct),
        "evaluated_at": _iso_utc(r.evaluated_at),
    }


def _snapshot_row_to_dict(r: PortfolioSnapshotRow) -> dict:
    return {
        "id": r.id,
        "source": r.source,
        "captured_at": _iso_utc(r.captured_at),
        "market_value": float(r.market_value),
        "cost_basis": float(r.cost_basis),
        "unrealized_pnl": float(r.unrealized_pnl),
        "unrealized_pnl_percent": float(r.unrealized_pnl_percent),
        "positions": int(r.positions or 0),
        "breakdown": r.breakdown,
    }


def _portfolio_row_to_dict(r: PortfolioPositionRow) -> dict:
    return {
        "id": r.id,
        "broker": r.broker,
        "symbol": r.symbol,
        "quantity": float(r.quantity),
        "avg_cost": float(r.avg_cost),
        "currency": r.currency,
        "opened_at": _iso_utc(r.opened_at),
        "notes": r.notes,
        "is_active": bool(r.is_active),
        "created_at": _iso_utc(r.created_at),
        "updated_at": _iso_utc(r.updated_at),
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
        tweet_list = [_sanitize_tweet_payload(t) for t in tweets]
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

    async def latest(
        self,
        limit: int = 50,
        before_id: int | None = None,
        options_only: bool = False,
        since_hours: int | None = None,
    ):
        stmt = select(TweetRow)
        if before_id is not None:
            stmt = stmt.where(TweetRow.id < before_id)
        if since_hours is not None:
            # SQLite rows are stored as naive UTC datetimes in this project.
            since_at = (
                datetime.now(timezone.utc) - timedelta(hours=since_hours)
            ).replace(tzinfo=None)
            stmt = stmt.where(TweetRow.created_at >= since_at)
        if options_only:
            stmt = stmt.where(TweetRow.is_options_tweet.is_(True))
        stmt = stmt.order_by(TweetRow.id.desc()).limit(limit)
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

    async def add_snapshot(self, payload: dict) -> dict:
        """Persist a point-in-time portfolio valuation.

        :param payload: Snapshot fields; ``captured_at`` defaults to now (UTC).
        :return: The stored snapshot as a dict.
        """
        row = PortfolioSnapshotRow(
            source=payload.get("source", "manual"),
            captured_at=payload.get("captured_at") or datetime.now(timezone.utc),
            market_value=float(payload.get("market_value", 0.0)),
            cost_basis=float(payload.get("cost_basis", 0.0)),
            unrealized_pnl=float(payload.get("unrealized_pnl", 0.0)),
            unrealized_pnl_percent=float(payload.get("unrealized_pnl_percent", 0.0)),
            positions=int(payload.get("positions", 0)),
            breakdown=payload.get("breakdown"),
        )
        async with self.Session() as s:
            async with s.begin():
                s.add(row)
            await s.refresh(row)
        return _snapshot_row_to_dict(row)

    async def list_snapshots(
        self,
        *,
        source: str | None = None,
        since: datetime | None = None,
        limit: int = 2000,
    ) -> list[dict]:
        """Return snapshots oldest-first, optionally filtered by source/date.

        :param source: Holdings source the snapshot was taken for.
        :param since: Only snapshots captured at or after this moment.
        :param limit: Maximum number of snapshots to return.
        """
        stmt = select(PortfolioSnapshotRow).order_by(
            PortfolioSnapshotRow.captured_at.asc()
        )
        if source is not None:
            stmt = stmt.where(PortfolioSnapshotRow.source == source)
        if since is not None:
            stmt = stmt.where(PortfolioSnapshotRow.captured_at >= since)
        stmt = stmt.limit(limit)

        async with self.Session() as s:
            rows = (await s.execute(stmt)).scalars().all()
        return [_snapshot_row_to_dict(r) for r in rows]

    async def latest_snapshot(self, *, source: str | None = None) -> dict | None:
        """Return the most recent snapshot, or ``None`` when none exist."""
        stmt = (
            select(PortfolioSnapshotRow)
            .order_by(PortfolioSnapshotRow.captured_at.desc())
            .limit(1)
        )
        if source is not None:
            stmt = stmt.where(PortfolioSnapshotRow.source == source)

        async with self.Session() as s:
            row = (await s.execute(stmt)).scalars().first()
        return _snapshot_row_to_dict(row) if row else None


def _gamma_exposure_row_to_dict(r: GammaExposureSnapshotRow) -> dict:
    return {
        "id": r.id,
        "symbol": r.symbol,
        "captured_at": _iso_utc(r.captured_at),
        "spot_price": float(r.spot_price),
        "net_gex": float(r.net_gex),
        "call_gex": float(r.call_gex) if r.call_gex is not None else None,
        "put_gex": float(r.put_gex) if r.put_gex is not None else None,
        "flip_point": float(r.flip_point) if r.flip_point is not None else None,
        "regime": r.regime,
    }


class GammaExposureRepo:
    """Async repo for stored dealer gamma exposure snapshots (issue #85)."""

    def __init__(self, session_factory: async_sessionmaker):
        self.Session = session_factory

    async def add_snapshot(self, payload: dict) -> dict:
        """Persist a point-in-time gamma exposure estimate.

        :param payload: Snapshot fields; ``captured_at`` defaults to now (UTC).
        :return: The stored snapshot as a dict.
        """
        row = GammaExposureSnapshotRow(
            symbol=str(payload.get("symbol", "SPY")).upper(),
            captured_at=payload.get("captured_at") or datetime.now(timezone.utc),
            spot_price=float(payload.get("spot_price", 0.0)),
            net_gex=float(payload.get("net_gex", 0.0)),
            call_gex=payload.get("call_gex"),
            put_gex=payload.get("put_gex"),
            flip_point=payload.get("flip_point"),
            regime=payload.get("regime", "positive"),
        )
        async with self.Session() as s:
            async with s.begin():
                s.add(row)
            await s.refresh(row)
        return _gamma_exposure_row_to_dict(row)

    async def list_snapshots(
        self,
        *,
        symbol: str = "SPY",
        since: datetime | None = None,
        limit: int = 2000,
    ) -> list[dict]:
        """Return snapshots oldest-first, optionally filtered by date.

        :param symbol: Underlying the snapshots were captured for.
        :param since: Only snapshots captured at or after this moment.
        :param limit: Maximum number of snapshots to return.
        """
        stmt = (
            select(GammaExposureSnapshotRow)
            .where(GammaExposureSnapshotRow.symbol == symbol.upper())
            .order_by(GammaExposureSnapshotRow.captured_at.asc())
        )
        if since is not None:
            stmt = stmt.where(GammaExposureSnapshotRow.captured_at >= since)
        stmt = stmt.limit(limit)

        async with self.Session() as s:
            rows = (await s.execute(stmt)).scalars().all()
        return [_gamma_exposure_row_to_dict(r) for r in rows]

    async def latest_snapshot(self, *, symbol: str = "SPY") -> dict | None:
        """Return the most recent snapshot for ``symbol``, or ``None``."""
        stmt = (
            select(GammaExposureSnapshotRow)
            .where(GammaExposureSnapshotRow.symbol == symbol.upper())
            .order_by(GammaExposureSnapshotRow.captured_at.desc())
            .limit(1)
        )
        async with self.Session() as s:
            row = (await s.execute(stmt)).scalars().first()
        return _gamma_exposure_row_to_dict(row) if row else None

    async def prune(self, *, symbol: str = "SPY", keep_days: int = 180) -> int:
        """Drop snapshots older than ``keep_days`` for ``symbol``."""
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=max(1, keep_days)
        )
        async with self.Session() as s:
            async with s.begin():
                result = await s.execute(
                    delete(GammaExposureSnapshotRow).where(
                        GammaExposureSnapshotRow.symbol == symbol.upper(),
                        GammaExposureSnapshotRow.captured_at < cutoff,
                    )
                )
        return result.rowcount or 0


def _ibkr_position_to_dict(r: IbkrPositionRow) -> dict:
    return {
        "id": r.id,
        "account": r.account,
        "symbol": r.symbol,
        "sec_type": r.sec_type,
        "exchange": r.exchange,
        "currency": r.currency,
        "quantity": float(r.quantity),
        "avg_cost": float(r.avg_cost),
        "synced_at": _iso_utc(r.synced_at),
    }


def _ibkr_trade_to_dict(r: IbkrTradeRow) -> dict:
    return {
        "id": r.id,
        "exec_id": r.exec_id,
        "account": r.account,
        "symbol": r.symbol,
        "sec_type": r.sec_type,
        "currency": r.currency,
        "side": r.side,
        "quantity": float(r.quantity),
        "price": float(r.price),
        "commission": float(r.commission) if r.commission is not None else None,
        "executed_at": _iso_utc(r.executed_at),
        "created_at": _iso_utc(r.created_at),
    }


class IbkrRepo:
    """Async repo for IBKR positions and trade executions."""

    def __init__(self, session_factory: async_sessionmaker):
        self.Session = session_factory

    async def sync_positions(self, account: str, positions: list[dict]) -> None:
        """Replace all positions for an account with the current snapshot."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        async with self.Session() as s:
            async with s.begin():
                await s.execute(
                    delete(IbkrPositionRow).where(IbkrPositionRow.account == account)
                )
                for p in positions:
                    s.add(IbkrPositionRow(**p, synced_at=now))

    async def list_positions(self) -> list[dict]:
        stmt = select(IbkrPositionRow).order_by(IbkrPositionRow.symbol.asc())
        async with self.Session() as s:
            rows = (await s.execute(stmt)).scalars().all()
        return [_ibkr_position_to_dict(r) for r in rows]

    async def upsert_trades(self, trades: list[dict]) -> int:
        """Insert new trade executions; skip duplicates by exec_id."""
        if not trades:
            return 0
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        async with self.Session() as s:
            async with s.begin():
                for t in trades:
                    executed_at = t.get("executed_at")
                    if isinstance(executed_at, datetime):
                        executed_at = executed_at.astimezone(timezone.utc).replace(
                            tzinfo=None
                        )
                    payload = {**t, "executed_at": executed_at, "created_at": now}
                    stmt = (
                        sqlite_insert(IbkrTradeRow)
                        .values(payload)
                        .on_conflict_do_nothing(index_elements=["exec_id"])
                    )
                    await s.execute(stmt)
        return len(trades)

    async def list_trades(
        self,
        limit: int = 50,
        before_id: int | None = None,
        min_value: float = 100.0,
    ) -> list[dict]:
        stmt = select(IbkrTradeRow)
        if before_id is not None:
            stmt = stmt.where(IbkrTradeRow.id < before_id)
        stmt = stmt.where(IbkrTradeRow.quantity * IbkrTradeRow.price >= min_value)
        stmt = stmt.order_by(IbkrTradeRow.id.desc()).limit(limit)
        async with self.Session() as s:
            rows = (await s.execute(stmt)).scalars().all()
        return [_ibkr_trade_to_dict(r) for r in rows]


class TraderCallRepo:
    """Async repo for trader credibility calls and their horizon results."""

    def __init__(self, session_factory: async_sessionmaker):
        self.Session = session_factory

    async def insert_calls(self, calls: Iterable[dict]) -> int:
        """Insert calls, skipping any (tweet_id, ticker) already recorded.

        :param calls: Dicts matching TraderCallRow fields (``created_at`` is
            stamped here, not by the caller).
        :return: Number of calls attempted (not all necessarily new).
        """
        call_list = list(calls)
        if not call_list:
            return 0

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        payload = [{**c, "created_at": now} for c in call_list]

        async with self.Session() as s:
            async with s.begin():
                stmt = (
                    sqlite_insert(TraderCallRow)
                    .values(payload)
                    .on_conflict_do_nothing(index_elements=["tweet_id", "ticker"])
                )
                await s.execute(stmt)
        return len(call_list)

    async def insert_results(self, results: Iterable[dict]) -> int:
        """Insert horizon results, skipping any (call_id, horizon_days) already graded.

        :param results: Dicts matching TraderCallResultRow fields.
        :return: Number of results attempted (not all necessarily new).
        """
        result_list = list(results)
        if not result_list:
            return 0

        async with self.Session() as s:
            async with s.begin():
                stmt = (
                    sqlite_insert(TraderCallResultRow)
                    .values(result_list)
                    .on_conflict_do_nothing(index_elements=["call_id", "horizon_days"])
                )
                await s.execute(stmt)
        return len(result_list)

    async def by_id(self, call_id: int) -> dict | None:
        stmt = select(TraderCallRow).where(TraderCallRow.id == call_id).limit(1)
        async with self.Session() as s:
            row = (await s.execute(stmt)).scalars().first()
        return _call_row_to_dict(row) if row else None

    async def results_for_call(self, call_id: int) -> list[dict]:
        stmt = select(TraderCallResultRow).where(TraderCallResultRow.call_id == call_id)
        async with self.Session() as s:
            rows = (await s.execute(stmt)).scalars().all()
        return [_result_row_to_dict(r) for r in rows]


def _epoch_to_naive_utc(value) -> datetime:
    """Convert the report's epoch-seconds timestamp to this project's convention.

    Timestamps are stored naive-UTC throughout (see the other repos here);
    ``TrendReport.generated_at`` is epoch seconds, so it needs converting
    rather than passing through.
    """
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(
            tzinfo=None
        )
    except (TypeError, ValueError, OSError, OverflowError):
        return datetime.now(timezone.utc).replace(tzinfo=None)


def _reddit_trend_row_to_dict(r: RedditTickerTrendRow) -> dict:
    return {
        "symbol": r.symbol,
        "rank": r.rank,
        "mentions": r.mentions,
        "previous_mentions": r.previous_mentions,
        "unique_authors": r.unique_authors,
        "score_sum": r.score_sum,
        "comment_sum": r.comment_sum,
        "engagement": r.engagement,
        "mentions_per_hour": r.mentions_per_hour,
        "momentum": r.momentum,
        "change_ratio": r.change_ratio,
        "spike_score": r.spike_score,
        "heat_score": r.heat_score,
        "sentiment": r.sentiment,
        "sentiment_score": r.sentiment_score,
        "sentiment_breakdown": r.sentiment_breakdown or {},
        "is_emerging": bool(r.is_emerging),
        "subreddits": r.subreddits or {},
        "sample_posts": r.sample_posts or [],
        "captured_at": _iso_utc(r.captured_at),
    }


def _reddit_run_row_to_dict(r: RedditTrendRunRow) -> dict:
    return {
        "id": r.id,
        "captured_at": _iso_utc(r.captured_at),
        "window_hours": r.window_hours,
        "baseline_hours": r.baseline_hours,
        "subreddits": r.subreddits or [],
        "posts_analyzed": r.posts_analyzed,
        "posts_in_window": r.posts_in_window,
        "mood": r.mood,
        "sentiment_score": r.sentiment_score,
        "sentiment_breakdown": r.sentiment_breakdown or {},
        "rising": r.rising or [],
        "fading": r.fading or [],
        "emerging": r.emerging or [],
        "by_subreddit": r.by_subreddit or [],
        "timeline": r.timeline or {},
    }


class RedditTrendRepo:
    """Async repo for stored Reddit trend runs and their ticker rankings."""

    def __init__(self, session_factory: async_sessionmaker):
        self.Session = session_factory

    async def save_report(self, report: dict) -> int:
        """Persist one trend report as a run plus its ranked tickers.

        :param report: A ``TrendReport.to_dict()`` payload.
        :return: The new run's id.
        """
        captured_at = _epoch_to_naive_utc(report.get("generated_at"))

        async with self.Session() as s:
            async with s.begin():
                run = RedditTrendRunRow(
                    captured_at=captured_at,
                    window_hours=float(report.get("window_hours") or 0.0),
                    baseline_hours=float(report.get("baseline_hours") or 0.0),
                    subreddits=list(report.get("subreddits") or []),
                    posts_analyzed=int(report.get("posts_analyzed") or 0),
                    posts_in_window=int(report.get("posts_in_window") or 0),
                    mood=report.get("mood"),
                    sentiment_score=report.get("sentiment_score"),
                    sentiment_breakdown=report.get("sentiment_breakdown") or {},
                    rising=list(report.get("rising") or []),
                    fading=list(report.get("fading") or []),
                    emerging=list(report.get("emerging") or []),
                    by_subreddit=list(report.get("by_subreddit") or []),
                    timeline=report.get("timeline") or {},
                )
                s.add(run)
                await s.flush()

                tickers = report.get("tickers") or []
                if tickers:
                    s.add_all(
                        [
                            RedditTickerTrendRow(
                                run_id=run.id,
                                captured_at=captured_at,
                                symbol=str(t.get("symbol") or ""),
                                rank=index,
                                mentions=int(t.get("mentions") or 0),
                                previous_mentions=int(t.get("previous_mentions") or 0),
                                unique_authors=int(t.get("unique_authors") or 0),
                                score_sum=int(t.get("score_sum") or 0),
                                comment_sum=int(t.get("comment_sum") or 0),
                                engagement=int(t.get("engagement") or 0),
                                mentions_per_hour=float(
                                    t.get("mentions_per_hour") or 0.0
                                ),
                                momentum=float(t.get("momentum") or 0.0),
                                change_ratio=t.get("change_ratio"),
                                spike_score=float(t.get("spike_score") or 0.0),
                                heat_score=float(t.get("heat_score") or 0.0),
                                sentiment=t.get("sentiment"),
                                sentiment_score=float(t.get("sentiment_score") or 0.0),
                                sentiment_breakdown=t.get("sentiment_breakdown") or {},
                                is_emerging=bool(t.get("is_emerging")),
                                subreddits=t.get("subreddits") or {},
                                sample_posts=t.get("sample_posts") or [],
                            )
                            for index, t in enumerate(tickers)
                            if t.get("symbol")
                        ]
                    )
                run_id = run.id
        return run_id

    async def latest_run(self, limit: int = 25) -> dict | None:
        """The most recent run with its ranked tickers, or ``None`` if never run."""
        run_stmt = (
            select(RedditTrendRunRow)
            .order_by(RedditTrendRunRow.captured_at.desc())
            .limit(1)
        )
        async with self.Session() as s:
            run = (await s.execute(run_stmt)).scalars().first()
            if run is None:
                return None

            ticker_stmt = (
                select(RedditTickerTrendRow)
                .where(RedditTickerTrendRow.run_id == run.id)
                .order_by(RedditTickerTrendRow.rank.asc())
                .limit(max(1, limit))
            )
            tickers = (await s.execute(ticker_stmt)).scalars().all()

        return {
            **_reddit_run_row_to_dict(run),
            "tickers": [_reddit_trend_row_to_dict(t) for t in tickers],
        }

    async def ticker_history(self, symbol: str, days: int = 30) -> list[dict]:
        """One ticker's ranking across recent runs, oldest first.

        This is the reason runs are kept rather than overwritten: a live scrape
        only reaches as far back as the listing pages still hold.
        """
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=max(1, days)
        )
        stmt = (
            select(RedditTickerTrendRow)
            .where(
                RedditTickerTrendRow.symbol == str(symbol).upper(),
                RedditTickerTrendRow.captured_at >= cutoff,
            )
            .order_by(RedditTickerTrendRow.captured_at.asc())
        )
        async with self.Session() as s:
            rows = (await s.execute(stmt)).scalars().all()
        return [_reddit_trend_row_to_dict(r) for r in rows]

    async def prune(self, keep_days: int = 90) -> int:
        """Drop runs older than *keep_days*, and the tickers that belong to them."""
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=max(1, keep_days)
        )
        async with self.Session() as s:
            async with s.begin():
                stale = (
                    (
                        await s.execute(
                            select(RedditTrendRunRow.id).where(
                                RedditTrendRunRow.captured_at < cutoff
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                if not stale:
                    return 0
                await s.execute(
                    delete(RedditTickerTrendRow).where(
                        RedditTickerTrendRow.run_id.in_(stale)
                    )
                )
                await s.execute(
                    delete(RedditTrendRunRow).where(RedditTrendRunRow.id.in_(stale))
                )
        return len(stale)
