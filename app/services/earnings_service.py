"""Nasdaq earnings calendar: which tickers report over the next N days.

Ported from fintwit-bot's `src/api/nasdaq.py:get_earnings_for_date` (used by
`src/cogs/loops/earnings_overview.py` for the weekly Discord earnings embed)
and `src/cogs/commands/earnings.py`. The Discord version posted one embed per
day; here a single endpoint returns the whole window so the frontend can
render it as a calendar strip.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, timedelta

import httpx

logger = logging.getLogger(__name__)

_NASDAQ_EARNINGS_URL = "https://api.nasdaq.com/api/calendar/earnings"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/market-activity/earnings",
}

# `time` on each Nasdaq row is one of these three literals.
_SESSION_MAP: dict[str, tuple[str, str]] = {
    "time-pre-market": ("pre-market", "🌅"),
    "time-after-hours": ("after-hours", "🌙"),
}

_CACHE_TTL_SECONDS = 900
_CACHE: dict[tuple[str, int, int], tuple[float, dict]] = {}


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").replace("$", "").strip()
    if not text or text.upper() in ("N/A", "NAN"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _coerce_int(value: object) -> int | None:
    parsed = _coerce_float(value)
    return int(parsed) if parsed is not None else None


def _parse_row(raw: dict, date_str: str) -> dict | None:
    symbol = str(raw.get("symbol") or "").strip().upper()
    if not symbol:
        return None

    session, session_emoji = _SESSION_MAP.get(
        str(raw.get("time") or ""), ("unknown", None)
    )

    return {
        "symbol": symbol,
        "name": str(raw.get("name") or "").strip() or None,
        "date": date_str,
        "session": session,
        "session_emoji": session_emoji,
        "market_cap": _coerce_float(raw.get("marketCap")),
        "eps_forecast": _coerce_float(raw.get("epsForecast")),
        "num_estimates": _coerce_int(raw.get("noOfEsts")),
        "fiscal_quarter_ending": str(raw.get("fiscalQuarterEnding") or "").strip()
        or None,
        "last_year_eps": _coerce_float(raw.get("lastYearEPS")),
        "last_year_report_date": str(raw.get("lastYearRptDt") or "").strip() or None,
        "website": f"https://www.nasdaq.com/market-activity/stocks/{symbol.lower()}/earnings",
    }


async def _fetch_day(
    client: httpx.AsyncClient, day: date
) -> tuple[str, list[dict], bool]:
    """Returns (date_str, rows, failed). `failed` is only set on a transport/HTTP
    error — a day with no earnings scheduled (e.g. a weekend) still counts as a
    successful fetch, just with zero rows.
    """
    date_str = day.isoformat()
    try:
        response = await client.get(
            _NASDAQ_EARNINGS_URL, params={"date": date_str}, headers=_HEADERS
        )
        if response.status_code != 200:
            logger.warning(
                "[earnings] Nasdaq request failed for %s: status=%s",
                date_str,
                response.status_code,
            )
            return date_str, [], True
        payload = response.json()
    except (httpx.RequestError, ValueError) as exc:
        logger.warning("[earnings] Nasdaq request failed for %s: %r", date_str, exc)
        return date_str, [], True

    data = payload.get("data") if isinstance(payload, dict) else None
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        # No `data`/`rows` key at all means Nasdaq has nothing for this date
        # (typical for weekends), not a failure.
        return date_str, [], False

    # Nasdaq already orders rows by market cap descending.
    parsed = [_parse_row(row, date_str) for row in rows if isinstance(row, dict)]
    return date_str, [row for row in parsed if row is not None], False


def _get_cached(key: tuple[str, int, int]) -> dict | None:
    cached = _CACHE.get(key)
    if cached is None:
        return None
    ts, payload = cached
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None
    return payload


def _set_cached(key: tuple[str, int, int], payload: dict) -> None:
    _CACHE[key] = (time.time(), payload)


def _reset_cache_for_tests() -> None:
    _CACHE.clear()


async def get_earnings_calendar(
    client: httpx.AsyncClient, days: int = 7, limit_per_day: int = 10
) -> dict | None:
    """Fetch the earnings calendar for the next `days` days, starting today.

    Returns `{start_date, end_date, days: [{date, count, rows}], source}`, or
    `None` if every day's request failed (transport/HTTP error) so the caller
    can distinguish "Nasdaq is unreachable" from "no earnings this week".
    """
    bounded_days = max(1, min(int(days), 14))
    bounded_limit = max(1, min(int(limit_per_day), 50))

    today = date.today()
    cache_key = (today.isoformat(), bounded_days, bounded_limit)
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    dates = [today + timedelta(days=i) for i in range(bounded_days)]
    results = await asyncio.gather(
        *[_fetch_day(client, d) for d in dates], return_exceptions=True
    )

    days_payload: list[dict] = []
    any_success = False
    for result, day in zip(results, dates):
        if isinstance(result, BaseException):
            days_payload.append({"date": day.isoformat(), "count": 0, "rows": []})
            continue

        date_str, rows, failed = result
        if not failed:
            any_success = True
        days_payload.append(
            {"date": date_str, "count": len(rows), "rows": rows[:bounded_limit]}
        )

    if not any_success:
        return None

    payload = {
        "start_date": dates[0].isoformat(),
        "end_date": dates[-1].isoformat(),
        "days": days_payload,
        "source": "nasdaq",
    }
    _set_cached(cache_key, payload)
    return payload
