"""Market hours service using exchange_calendars (offline, no external API)."""

import logging
import time

import exchange_calendars as xcals
import pandas as pd

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 60

# (display_name, xcals_calendar_name, local_timezone, has_us_extended_hours)
_EXCHANGES: list[tuple[str, str, str, bool]] = [
    ("NYSE", "XNYS", "America/New_York", True),
    ("NASDAQ", "XNAS", "America/New_York", True),
    ("LSE", "XLON", "Europe/London", False),
    ("JPX", "XTKS", "Asia/Tokyo", False),
    ("HKEX", "XHKG", "Asia/Hong_Kong", False),
]

# US extended-hours windows as (hour, minute) tuples in Eastern Time
_US_PRE_MARKET_START = (4, 0)
_US_PRE_MARKET_END = (9, 30)
_US_AFTER_HOURS_START = (16, 0)
_US_AFTER_HOURS_END = (20, 0)

_calendars: dict[str, xcals.ExchangeCalendar] = {}
_cache: tuple[float, list[dict]] | None = None


def _reset_cache_for_tests() -> None:
    global _cache
    _cache = None


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _get_calendar(name: str) -> xcals.ExchangeCalendar:
    if name not in _calendars:
        _calendars[name] = xcals.get_calendar(name)
    return _calendars[name]


def _ts_to_iso(ts: pd.Timestamp | None) -> str | None:
    if ts is None:
        return None
    return ts.isoformat()


def _build_row(display: str, xcals_name: str, tz_name: str, is_us: bool) -> dict:
    cal = _get_calendar(xcals_name)
    now = _now_utc()

    try:
        is_regular_open = cal.is_open_on_minute(now)
    except Exception:
        is_regular_open = False

    session = "Closed"
    is_open = False

    if is_regular_open:
        session = "Open"
        is_open = True
    elif is_us:
        local = now.tz_convert(tz_name)
        h, m = local.hour, local.minute

        in_pre = _US_PRE_MARKET_START <= (h, m) < _US_PRE_MARKET_END
        in_ah = _US_AFTER_HOURS_START <= (h, m) < _US_AFTER_HOURS_END

        if in_pre or in_ah:
            try:
                today_is_session = cal.is_session(str(local.date()))
            except Exception:
                today_is_session = False

            if in_pre and today_is_session:
                session = "Pre-market"
                is_open = True
            elif in_ah and today_is_session:
                session = "After-hours"
                is_open = True

    next_open: pd.Timestamp | None = None
    next_close: pd.Timestamp | None = None

    try:
        if is_regular_open:
            current_session = cal.minute_to_session(now)
            next_close = cal.session_close(current_session)
        else:
            next_open = cal.next_open(now)
    except Exception as exc:
        logger.debug("[market_hours] next event error for %s: %r", display, exc)

    closure_reason: str | None = None
    is_holiday = False

    if session == "Closed":
        local_dt = now.tz_convert(tz_name)
        if local_dt.day_of_week >= 5:  # Saturday=5, Sunday=6
            closure_reason = "weekend"
        else:
            try:
                if not cal.is_session(str(local_dt.date())):
                    closure_reason = "holiday"
                    is_holiday = True
            except Exception:
                pass

    return {
        "exchange": display,
        "session": session,
        "is_open": is_open,
        "as_of": now.isoformat(),
        "timezone": tz_name,
        "next_open": _ts_to_iso(next_open),
        "next_close": _ts_to_iso(next_close),
        "closure_reason": closure_reason,
        "is_holiday": is_holiday,
        "holiday_name": None,
    }


async def get_stock_market_hours(
    client=None,  # unused; kept for backward compatibility
) -> list[dict] | None:
    """Return current session state for major exchanges using exchange_calendars."""
    global _cache

    if _cache is not None:
        ts, cached_rows = _cache
        if time.time() - ts < _CACHE_TTL_SECONDS:
            return cached_rows

    try:
        rows = [
            _build_row(display, xcals_name, tz_name, is_us)
            for display, xcals_name, tz_name, is_us in _EXCHANGES
        ]
        _cache = (time.time(), rows)
        return rows
    except Exception as exc:
        logger.warning("[market_hours] failed to compute: %r", exc)
        return _cache[1] if _cache is not None else None
