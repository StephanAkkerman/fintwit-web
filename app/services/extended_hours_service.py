"""Extended-hours snapshot: window bounds, US equity futures, ETF prices, tweet stats."""

import asyncio
import logging
import time
from datetime import datetime, time as dt_time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import async_sessionmaker
from ticker_price_data import get_stock_info
from ticker_price_data.market_session import get_us_stock_session
from ticker_price_data.tradingview_quote import get_tradingview_quote

from .mention_aggregator import get_extended_hours_stats

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

_FUTURES: list[tuple[str, str]] = [
    ("ES", "CME_MINI:ES1!"),
    ("NQ", "CME_MINI:NQ1!"),
    ("YM", "CBOT_MINI:YM1!"),
]
_ETFS: list[str] = ["SPY", "QQQ", "IWM"]

_CACHE_TTL = 180  # seconds
_snapshot_cache: tuple[float, dict] | None = None
_lock = asyncio.Lock()


def _to_naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _window_bounds(session: str) -> tuple[str, str, datetime, datetime]:
    """Return (window_start_iso, window_end_iso, since_naive_utc, until_naive_utc)."""
    now_et = datetime.now(_ET)
    today = now_et.date()

    if session == "pre-market":
        start = datetime.combine(today, dt_time(4, 0), tzinfo=_ET)
        end = datetime.combine(today, dt_time(9, 30), tzinfo=_ET)
    elif session == "after-hours":
        start = datetime.combine(today, dt_time(16, 0), tzinfo=_ET)
        end = datetime.combine(today, dt_time(20, 0), tzinfo=_ET)
    elif session == "regular":
        # Most-recently completed session before open: today's pre-market.
        start = datetime.combine(today, dt_time(4, 0), tzinfo=_ET)
        end = datetime.combine(today, dt_time(9, 30), tzinfo=_ET)
    else:
        # closed (overnight, weekend, holiday)
        # Before 4 PM: last completed after-hours was yesterday's.
        # At or after 4 PM: today's after-hours window (or in progress).
        if now_et.hour < 16:
            yesterday = today - timedelta(days=1)
            start = datetime.combine(yesterday, dt_time(16, 0), tzinfo=_ET)
            end = datetime.combine(yesterday, dt_time(20, 0), tzinfo=_ET)
        else:
            start = datetime.combine(today, dt_time(16, 0), tzinfo=_ET)
            end = datetime.combine(today, dt_time(20, 0), tzinfo=_ET)

    return (
        start.isoformat(),
        end.isoformat(),
        _to_naive_utc(start),
        _to_naive_utc(end),
    )


async def _fetch_futures() -> list[dict]:
    sem = asyncio.Semaphore(3)

    async def _one(label: str, symbol: str) -> dict | None:
        async with sem:
            try:
                result = await get_tradingview_quote(symbol, asset_hint="index")
                if not isinstance(result, dict):
                    return None
                price = result.get("price")
                if not isinstance(price, (int, float)):
                    return None
                return {
                    "label": label,
                    "symbol": symbol,
                    "price": float(price),
                    "change_pct": float(result.get("change_percent") or 0.0),
                }
            except Exception as exc:
                logger.debug("[extended-hours] futures %s failed: %r", symbol, exc)
                return None

    results = await asyncio.gather(*[_one(lbl, sym) for lbl, sym in _FUTURES])
    return [r for r in results if r is not None]


async def _fetch_etfs() -> list[dict]:
    sem = asyncio.Semaphore(3)

    async def _one(symbol: str) -> dict | None:
        async with sem:
            try:
                result = await get_stock_info(symbol)
                if not isinstance(result, dict):
                    return None
                price = result.get("price")
                if not isinstance(price, (int, float)):
                    return None
                ext_price = result.get("extended_price")
                ext_pct = result.get("extended_change_percent")
                return {
                    "symbol": symbol,
                    "price": float(price),
                    "extended_price": float(ext_price)
                    if ext_price is not None
                    else None,
                    "extended_change_pct": float(ext_pct)
                    if ext_pct is not None
                    else None,
                }
            except Exception as exc:
                logger.debug("[extended-hours] ETF %s failed: %r", symbol, exc)
                return None

    results = await asyncio.gather(*[_one(s) for s in _ETFS])
    return [r for r in results if r is not None]


async def get_snapshot(Session: async_sessionmaker) -> dict | None:
    global _snapshot_cache

    async with _lock:
        if _snapshot_cache is not None:
            ts, payload = _snapshot_cache
            if time.time() - ts < _CACHE_TTL:
                return payload

        try:
            session = get_us_stock_session()
            window_start_iso, window_end_iso, since_dt, until_dt = _window_bounds(
                session
            )

            futures, etfs, tweet_stats = await asyncio.gather(
                _fetch_futures(),
                _fetch_etfs(),
                get_extended_hours_stats(Session, since_dt, until_dt),
            )

            payload = {
                "session": session,
                "window_start": window_start_iso,
                "window_end": window_end_iso,
                "futures": futures,
                "etfs": etfs,
                "tweet_stats": tweet_stats,
            }
            _snapshot_cache = (time.time(), payload)
            return payload
        except Exception as exc:
            logger.warning("[extended-hours] snapshot failed: %r", exc)
            return _snapshot_cache[1] if _snapshot_cache is not None else None
