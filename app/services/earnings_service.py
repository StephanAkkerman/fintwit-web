"""Nasdaq earnings calendar: which tickers report over the next N days, and
what the ones that already reported posted against their estimate.

Ported from fintwit-bot's `src/api/nasdaq.py:get_earnings_for_date` (used by
`src/cogs/loops/earnings_overview.py` for the weekly Discord earnings embed)
and `src/cogs/commands/earnings.py`. The Discord version posted one embed per
day; here a single endpoint returns the whole window so the frontend can
render it as a calendar strip.

Results (fintwit-bot issue #296) come from the same Nasdaq endpoint: for a
date that has passed, each row also carries the reported EPS and Nasdaq's
surprise percentage. The bot only relayed EPSGUID tweets into its news
channel; `get_earnings_results` turns those rows into a beat/miss list.
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
_CACHE: dict[tuple, tuple[float, dict]] = {}
#: Rows per date, shared by every window and limit so a 14-day request and a
#: 1-day request don't each hit Nasdaq for today.
_DAY_CACHE: dict[str, tuple[float, list[dict]]] = {}
#: How long a day's last good rows stand in when Nasdaq fails for it.
_STALE_TTL_SECONDS = 86400
#: Nasdaq starts refusing a burst of 14 parallel requests; keep it to a few.
_NASDAQ_CONCURRENCY = 4
_nasdaq_slots = asyncio.Semaphore(_NASDAQ_CONCURRENCY)
_RETRY_DELAY_SECONDS = 1.0

#: A surprise within this many percent of the estimate counts as in line.
INLINE_SURPRISE_PCT = 1.0


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
        "eps_actual": _coerce_float(raw.get("eps")),
        "surprise_pct": _coerce_float(raw.get("surprise")),
        "website": f"https://www.nasdaq.com/market-activity/stocks/{symbol.lower()}/earnings",
    }


async def _request_day(
    client: httpx.AsyncClient, date_str: str
) -> tuple[list[dict], bool]:
    """One Nasdaq request: ``(rows, failed)``."""
    try:
        async with _nasdaq_slots:
            response = await client.get(
                _NASDAQ_EARNINGS_URL, params={"date": date_str}, headers=_HEADERS
            )
        if response.status_code != 200:
            logger.warning(
                "[earnings] Nasdaq request failed for %s: status=%s",
                date_str,
                response.status_code,
            )
            return [], True
        payload = response.json()
    except (httpx.RequestError, ValueError) as exc:
        logger.warning("[earnings] Nasdaq request failed for %s: %r", date_str, exc)
        return [], True

    data = payload.get("data") if isinstance(payload, dict) else None
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        # No `data`/`rows` key at all means Nasdaq has nothing for this date
        # (typical for weekends), not a failure.
        return [], False

    # Nasdaq already orders rows by market cap descending.
    parsed = [_parse_row(row, date_str) for row in rows if isinstance(row, dict)]
    return [row for row in parsed if row is not None], False


async def _fetch_day(
    client: httpx.AsyncClient, day: date
) -> tuple[str, list[dict], bool]:
    """Returns (date_str, rows, failed). `failed` is only set on a transport/HTTP
    error — a day with no earnings scheduled (e.g. a weekend) still counts as a
    successful fetch, just with zero rows.

    A failed request is retried once; if that fails too, the day's last good
    rows (up to a day old) are returned instead of a failure.
    """
    date_str = day.isoformat()
    cached = _DAY_CACHE.get(date_str)
    if cached and time.time() - cached[0] <= _CACHE_TTL_SECONDS:
        return date_str, cached[1], False

    rows, failed = await _request_day(client, date_str)
    if failed:
        await asyncio.sleep(_RETRY_DELAY_SECONDS)
        rows, failed = await _request_day(client, date_str)
    if not failed:
        _DAY_CACHE[date_str] = (time.time(), rows)
        return date_str, rows, False
    if cached and time.time() - cached[0] <= _STALE_TTL_SECONDS:
        return date_str, cached[1], False
    return date_str, [], True


def _get_cached(key: tuple) -> dict | None:
    cached = _CACHE.get(key)
    if cached is None:
        return None
    ts, payload = cached
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None
    return payload


def _set_cached(key: tuple, payload: dict) -> None:
    _CACHE[key] = (time.time(), payload)


def _reset_cache_for_tests() -> None:
    _CACHE.clear()
    _DAY_CACHE.clear()


async def get_earnings_calendar(
    client: httpx.AsyncClient, days: int = 7, limit_per_day: int = 10
) -> dict | None:
    """Fetch the earnings calendar for the next `days` days, starting today.

    Returns `{start_date, end_date, days: [{date, count, rows}], source}`, plus
    `failed_dates` when Nasdaq failed for some days (their rows are empty, not
    known to be empty), or `None` if every day's request failed
    (transport/HTTP error) so the caller can distinguish "Nasdaq is
    unreachable" from "no earnings this week".
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
    failed_dates: list[str] = []
    any_success = False
    for result, day in zip(results, dates):
        if isinstance(result, BaseException):
            failed_dates.append(day.isoformat())
            days_payload.append({"date": day.isoformat(), "count": 0, "rows": []})
            continue

        date_str, rows, failed = result
        if failed:
            failed_dates.append(date_str)
        else:
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
    if failed_dates:
        # A failed day reads as "no earnings" otherwise; say it is unknown,
        # and don't cache the gap.
        payload["failed_dates"] = failed_dates
        return payload
    _set_cached(cache_key, payload)
    return payload


def classify_result(row: dict) -> dict | None:
    """Add ``surprise_pct`` and ``outcome`` to a row that has reported.

    Nasdaq's own surprise is kept when it sent one; otherwise it is worked out
    from the actual and the consensus. ``outcome`` is ``beat``, ``miss`` or
    ``inline`` (within ``INLINE_SURPRISE_PCT``), or ``None`` when there was no
    estimate to compare with.

    :return: the enriched row, or ``None`` when the row has no reported EPS.
    """
    actual = row.get("eps_actual")
    if actual is None:
        return None
    forecast = row.get("eps_forecast")
    surprise = row.get("surprise_pct")
    if surprise is None and forecast not in (None, 0):
        surprise = round((actual - forecast) / abs(forecast) * 100, 2)

    if surprise is not None:
        if abs(surprise) < INLINE_SURPRISE_PCT:
            outcome = "inline"
        else:
            outcome = "beat" if surprise > 0 else "miss"
    elif forecast is not None:
        outcome = (
            "beat" if actual > forecast else "miss" if actual < forecast else "inline"
        )
    else:
        outcome = None
    return {**row, "surprise_pct": surprise, "outcome": outcome}


async def get_earnings_results(
    client: httpx.AsyncClient, days: int = 5, limit: int = 30
) -> dict | None:
    """Companies that reported over the last `days` weekdays, newest day first.

    Within a day rows keep Nasdaq's market-cap order, so the largest reports
    come first.

    :return: ``{start_date, end_date, results, summary: {reported, beat, miss,
        inline}, source}``, or ``None`` when every day's request failed.
    """
    bounded_days = max(1, min(int(days), 14))
    bounded_limit = max(1, min(int(limit), 100))

    today = date.today()
    cache_key = ("results", today.isoformat(), bounded_days, bounded_limit)
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    # Count trading days, not calendar days: a Monday look-back of 5 should
    # still reach the previous Tuesday instead of spending two on a weekend.
    dates: list[date] = []
    day = today
    while len(dates) < bounded_days:
        if day.weekday() < 5:
            dates.append(day)
        day -= timedelta(days=1)
    fetched = await asyncio.gather(
        *[_fetch_day(client, d) for d in dates], return_exceptions=True
    )

    results: list[dict] = []
    any_success = False
    for item in fetched:
        if isinstance(item, BaseException):
            continue
        _, rows, failed = item
        if not failed:
            any_success = True
        results.extend(r for r in map(classify_result, rows) if r is not None)

    if not any_success:
        return None

    summary = {"reported": len(results), "beat": 0, "miss": 0, "inline": 0}
    for row in results:
        if row["outcome"] in ("beat", "miss", "inline"):
            summary[row["outcome"]] += 1

    payload = {
        "start_date": dates[-1].isoformat(),
        "end_date": dates[0].isoformat(),
        "results": results[:bounded_limit],
        "summary": summary,
        "source": "nasdaq",
    }
    _set_cached(cache_key, payload)
    return payload
