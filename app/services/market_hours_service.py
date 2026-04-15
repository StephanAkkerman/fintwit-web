"""Market hours service using the exchange_calendars package.

No external HTTP calls — all session state is derived from the published
exchange schedules bundled with exchange_calendars.
"""

import asyncio
import logging
from datetime import datetime, timezone
from datetime import time as dt_time
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

logger = logging.getLogger(__name__)

# (display_name, exchange_calendars MIC code, IANA timezone)
_EXCHANGES: list[tuple[str, str, str]] = [
    ("NYSE", "XNYS", "America/New_York"),
    ("NASDAQ", "XNAS", "America/New_York"),
    ("LSE", "XLON", "Europe/London"),
    ("JPX", "XTKS", "Asia/Tokyo"),
    ("HKEX", "XHKG", "Asia/Hong_Kong"),
]

# Exchanges with extended (pre-market / after-hours) sessions.
# All times are LOCAL exchange time.
_EXTENDED: dict[str, dict[str, dt_time]] = {
    "XNYS": {"pre_start": dt_time(4, 0), "post_end": dt_time(20, 0)},
    "XNAS": {"pre_start": dt_time(4, 0), "post_end": dt_time(20, 0)},
}


def _holiday_name_from_calendar(cal, session_date: pd.Timestamp) -> str | None:
    """Return holiday name for a non-session date when available."""
    regular_holidays = getattr(cal, "regular_holidays", None)
    if regular_holidays is not None:
        try:
            names = regular_holidays.holidays(
                start=session_date, end=session_date, return_name=True
            )
            if hasattr(names, "empty") and not names.empty:
                if hasattr(names, "iloc"):
                    return str(names.iloc[0])
                return str(names[0])
        except Exception:
            logger.debug("Could not read regular holiday names", exc_info=True)

    for holiday_date in getattr(cal, "adhoc_holidays", []) or []:
        try:
            if pd.Timestamp(holiday_date).date() == pd.Timestamp(session_date).date():
                return "Ad-hoc market holiday"
        except Exception:
            continue

    return None


def _closed_context(cal, local_now: datetime, session_date: pd.Timestamp) -> dict:
    """Describe why an exchange is closed, if known."""
    if cal.is_session(session_date):
        return {
            "closure_reason": None,
            "is_holiday": False,
            "holiday_name": None,
        }

    if local_now.weekday() >= 5:
        return {
            "closure_reason": "weekend",
            "is_holiday": False,
            "holiday_name": None,
        }

    holiday_name = _holiday_name_from_calendar(cal, session_date)
    return {
        "closure_reason": "holiday",
        "is_holiday": True,
        "holiday_name": holiday_name,
    }


def _session_info(cal_id: str, tz_name: str, now_utc: pd.Timestamp) -> dict:
    """Return session state dict for one exchange."""
    try:
        cal = xcals.get_calendar(cal_id)
        tz = ZoneInfo(tz_name)
        local_now = now_utc.to_pydatetime().astimezone(tz)
        local_date = local_now.date()
        local_time = local_now.time()
        today_ts = pd.Timestamp(local_date)

        # ── Regular session ──────────────────────────────────────────────────
        if cal.is_open_at_time(now_utc):
            return {
                "session": "Open",
                "is_open": True,
                "next_open": None,
                "next_close": cal.next_close(now_utc).isoformat(),
                "closure_reason": None,
                "is_holiday": False,
                "holiday_name": None,
            }

        # ── Extended hours (pre-market / after-hours) ─────────────────────
        ext = _EXTENDED.get(cal_id)
        if ext:
            if cal.is_session(today_ts):
                open_local = (
                    cal.session_open(today_ts).to_pydatetime().astimezone(tz).time()
                )
                close_local = (
                    cal.session_close(today_ts).to_pydatetime().astimezone(tz).time()
                )

                if ext["pre_start"] <= local_time < open_local:
                    close_dt = datetime.combine(local_date, open_local).replace(
                        tzinfo=tz
                    )
                    return {
                        "session": "Pre-market",
                        "is_open": True,
                        "next_open": None,
                        "next_close": close_dt.isoformat(),
                        "closure_reason": None,
                        "is_holiday": False,
                        "holiday_name": None,
                    }

                if close_local <= local_time < ext["post_end"]:
                    close_dt = datetime.combine(
                        local_date, ext["post_end"]
                    ).replace(tzinfo=tz)
                    return {
                        "session": "After-hours",
                        "is_open": True,
                        "next_open": None,
                        "next_close": close_dt.isoformat(),
                        "closure_reason": None,
                        "is_holiday": False,
                        "holiday_name": None,
                    }

        # ── Closed ────────────────────────────────────────────────────────────
        next_regular_open = cal.next_open(now_utc)
        closed_context = _closed_context(cal, local_now, today_ts)

        # For extended-hours exchanges show pre-market start as next open
        if ext:
            tz = ZoneInfo(tz_name)
            next_open_local = next_regular_open.to_pydatetime().astimezone(tz)
            pre_start_dt = datetime.combine(
                next_open_local.date(), ext["pre_start"]
            ).replace(tzinfo=tz)
            now_aware = local_now
            if pre_start_dt > now_aware:
                return {
                    "session": "Closed",
                    "is_open": False,
                    "next_open": pre_start_dt.isoformat(),
                    "next_close": None,
                    **closed_context,
                }

        return {
            "session": "Closed",
            "is_open": False,
            "next_open": next_regular_open.isoformat(),
            "next_close": None,
            **closed_context,
        }

    except Exception as exc:
        logger.warning("exchange_calendars error for %s: %s", cal_id, exc)
        return {
            "session": "Unknown",
            "is_open": False,
            "next_open": None,
            "next_close": None,
            "closure_reason": None,
            "is_holiday": False,
            "holiday_name": None,
        }


def _build_market_hours() -> list[dict]:
    now = pd.Timestamp.now(tz="UTC")
    as_of = datetime.now(timezone.utc).isoformat()

    results: list[dict] = []
    for name, cal_id, tz_name in _EXCHANGES:
        info = _session_info(cal_id, tz_name, now)
        results.append({"exchange": name, "timezone": tz_name, "as_of": as_of, **info})
    return results


async def get_stock_market_hours() -> list[dict]:
    """Return current session state for major exchanges.

    Runs the synchronous exchange_calendars calls in a thread so the async
    event loop is not blocked during calendar initialisation.
    """
    return await asyncio.to_thread(_build_market_hours)


if __name__ == "__main__":

    async def main() -> None:
        rows = await get_stock_market_hours()
        for row in rows:
            print(row)

    asyncio.run(main())
