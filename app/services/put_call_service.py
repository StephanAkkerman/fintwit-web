"""Cboe market-wide put/call ratios (fintwit-bot issue #738).

The `/options` overview's ratio only sums the puts and calls of a short
watchlist (SPY, QQQ, a few mega caps). The ratio traders quote is Cboe's own:
total, equity-only and index put/call volume across every listed contract.

Cboe publishes each session's statistics as a JSON file on its CDN, one file
per trading day (`{YYYY-MM-DD}_daily_options`), with no key. Days without a
session (weekends, holidays, today before the close) answer 403, so the
service walks back over recent weekdays and keeps the ones that exist.

The equity ratio is the usual sentiment read: a high ratio means traders are
buying protection (fear, often contrarian bullish), a low one means they are
chasing calls (complacency). The thresholds below are the commonly quoted
rules of thumb, not a statistical model.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, timedelta

import httpx

logger = logging.getLogger(__name__)

_CBOE_DAILY_URL = (
    "https://cdn.cboe.com/data/us/options/market_statistics/daily/{day}_daily_options"
)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}
_CACHE_TTL_SECONDS = 3600  # one file per session; nothing changes intraday
_CONCURRENCY = 6

#: Trading sessions kept for the history sparkline and the averages.
HISTORY_SESSIONS = 20
#: Weekdays scanned to find that many sessions (covers holidays).
_LOOKBACK_WEEKDAYS = 26

#: Cboe's ratio names -> the keys this API returns.
RATIO_KEYS: dict[str, str] = {
    "TOTAL PUT/CALL RATIO": "total",
    "EQUITY PUT/CALL RATIO": "equity",
    "INDEX PUT/CALL RATIO": "index",
    "EXCHANGE TRADED PRODUCTS PUT/CALL RATIO": "etp",
    "SPX + SPXW PUT/CALL RATIO": "spx",
    "CBOE VOLATILITY INDEX (VIX) PUT/CALL RATIO": "vix",
}
#: Cboe's volume sections -> the keys this API returns.
VOLUME_KEYS: dict[str, str] = {
    "SUM OF ALL PRODUCTS": "total",
    "EQUITY OPTIONS": "equity",
    "INDEX OPTIONS": "index",
}

#: Equity put/call at or above this reads as fearful, at or below as complacent.
EQUITY_FEAR_THRESHOLD = 0.80
EQUITY_GREED_THRESHOLD = 0.50

_cache: tuple[float, dict] | None = None


def _reset_cache_for_tests() -> None:
    global _cache
    _cache = None


def _to_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _to_int(value: object) -> int | None:
    parsed = _to_float(value)
    return int(parsed) if parsed is not None else None


def parse_daily(payload: dict, day: str) -> dict | None:
    """Turn one Cboe daily file into ``{date, ratios, volume}``.

    :param payload: the JSON Cboe returned for that session.
    :param day: the session date, ``YYYY-MM-DD``.
    :return: the parsed session, or ``None`` when it carries no total ratio.
    """
    ratios: dict[str, float] = {}
    for item in payload.get("ratios") or []:
        if not isinstance(item, dict):
            continue
        key = RATIO_KEYS.get(str(item.get("name") or "").strip().upper())
        value = _to_float(item.get("value"))
        if key and value is not None:
            ratios[key] = value
    if "total" not in ratios:
        return None

    volume: dict[str, dict[str, int | None]] = {}
    for section, key in VOLUME_KEYS.items():
        for row in payload.get(section) or []:
            if isinstance(row, dict) and str(row.get("name")).upper() == "VOLUME":
                volume[key] = {
                    "call": _to_int(row.get("call")),
                    "put": _to_int(row.get("put")),
                }
    return {"date": day, "ratios": ratios, "volume": volume}


def classify_equity_ratio(value: float | None) -> str | None:
    """``fear`` / ``neutral`` / ``greed`` from the equity put/call ratio."""
    if value is None:
        return None
    if value >= EQUITY_FEAR_THRESHOLD:
        return "fear"
    if value <= EQUITY_GREED_THRESHOLD:
        return "greed"
    return "neutral"


def _recent_weekdays(today: date, count: int) -> list[date]:
    days: list[date] = []
    day = today
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    return days


async def _fetch_day(
    client: httpx.AsyncClient, day: date, sem: asyncio.Semaphore
) -> dict | None:
    url = _CBOE_DAILY_URL.format(day=day.isoformat())
    async with sem:
        try:
            response = await client.get(url, headers=_HEADERS, timeout=15)
        except httpx.RequestError as exc:
            logger.warning("[put-call] Cboe request failed for %s: %r", day, exc)
            return None
    # 403 is how the CDN answers a date with no file (no session yet).
    if response.status_code != 200:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    return parse_daily(payload, day.isoformat())


def build_summary(sessions: list[dict]) -> dict | None:
    """Latest ratios plus averages and history over the given sessions.

    :param sessions: parsed sessions, newest first.
    """
    if not sessions:
        return None
    latest = sessions[0]
    window = sessions[:HISTORY_SESSIONS]

    def average(key: str) -> float | None:
        values = [s["ratios"][key] for s in window if key in s["ratios"]]
        return round(sum(values) / len(values), 3) if values else None

    previous = sessions[1]["ratios"] if len(sessions) > 1 else {}
    ratios = []
    for key in RATIO_KEYS.values():
        value = latest["ratios"].get(key)
        if value is None:
            continue
        prev = previous.get(key)
        ratios.append(
            {
                "key": key,
                "value": value,
                "previous": prev,
                "change": round(value - prev, 3) if prev is not None else None,
                "average": average(key),
            }
        )

    equity = latest["ratios"].get("equity")
    return {
        "date": latest["date"],
        "ratios": ratios,
        "volume": latest["volume"],
        "sentiment": classify_equity_ratio(equity),
        "thresholds": {
            "fear": EQUITY_FEAR_THRESHOLD,
            "greed": EQUITY_GREED_THRESHOLD,
        },
        "history": [
            {
                "date": s["date"],
                "total": s["ratios"].get("total"),
                "equity": s["ratios"].get("equity"),
                "index": s["ratios"].get("index"),
            }
            for s in reversed(window)
        ],
        "source": "cboe",
    }


async def get_put_call_ratios(client: httpx.AsyncClient) -> dict | None:
    """Cboe total/equity/index put/call ratios for the latest session.

    :return: ``{date, ratios: [{key, value, previous, change, average}], volume,
        sentiment, thresholds, history: [{date, total, equity, index}], source}``
        with history oldest first, or ``None`` when Cboe returned nothing.
    """
    global _cache
    if _cache and time.time() - _cache[0] <= _CACHE_TTL_SECONDS:
        return _cache[1]

    sem = asyncio.Semaphore(_CONCURRENCY)
    days = _recent_weekdays(date.today(), _LOOKBACK_WEEKDAYS)
    results = await asyncio.gather(
        *[_fetch_day(client, day, sem) for day in days], return_exceptions=True
    )
    sessions = [r for r in results if isinstance(r, dict)]
    summary = build_summary(sessions)
    if summary is None:
        return None
    _cache = (time.time(), summary)
    return summary
