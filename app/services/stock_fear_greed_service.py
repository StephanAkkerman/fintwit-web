"""Stock market Fear & Greed Index client (feargreedmeter.com).

feargreedmeter.com is a CNN-style Fear & Greed Index clone; its backend at
``api2.mmeter.app`` is undocumented. A recorded response nests today's score
at ``payload["fgi"]["latest"]["now"]`` (with the prior close alongside it as
``previous_close``). ``_find_summary`` is deliberately tolerant of a few other
plausible shapes too (a flat top-level object, or one nested one level under
a ``fear_and_greed``/``stock``/``stocks`` key) and the service returns
``None`` rather than raising if none of them match, so an upstream schema
change degrades to "unavailable" instead of a crash.
"""

import logging
import time
from datetime import date, datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

_URL = "https://api2.mmeter.app/data/summary"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://feargreedmeter.com/",
    "Origin": "https://feargreedmeter.com",
}

_CACHE_TTL_SECONDS = 300
_cache: tuple[float, dict] | None = None
# The raw upstream ``latest`` block behind ``_cache``; its week/month-ago
# readings are the history fallback when CNN's series is unavailable.
_latest_cache: dict | None = None

# CNN's Fear & Greed graph data: daily readings from the date in the path.
_HISTORY_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{start}"
_HISTORY_HEADERS = {
    "User-Agent": _HEADERS["User-Agent"],
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://edition.cnn.com/",
    "Origin": "https://edition.cnn.com",
}
_HISTORY_CACHE_TTL_SECONDS = 1800
_history_cache: dict[int, tuple[float, dict]] = {}
HISTORY_WINDOWS = (7, 30)

# (inclusive upper bound, label), standard 0-100 Fear & Greed scale.
_BUCKETS = (
    (25, "Extreme Fear"),
    (40, "Fear"),
    (60, "Neutral"),
    (75, "Greed"),
    (100, "Extreme Greed"),
)

_SUMMARY_KEYS = (
    "fear_and_greed",
    "stock",
    "stocks",
    "data",
    "summary",
    "result",
    "fgi",
)
_SCORE_KEYS = ("score", "value", "now")


def _reset_cache_for_tests() -> None:
    global _cache, _latest_cache
    _cache = None
    _latest_cache = None
    _history_cache.clear()


def _classify(score: float) -> str:
    for upper, label in _BUCKETS:
        if score <= upper:
            return label
    return "Extreme Greed"


def _coerce_score(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _first(d: dict, *keys: str) -> object | None:
    for key in keys:
        if d.get(key) is not None:
            return d[key]
    return None


def _find_summary(payload: dict) -> dict | None:
    candidates = [payload]
    for key in _SUMMARY_KEYS:
        nested = payload.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)
            latest = nested.get("latest")
            if isinstance(latest, dict):
                candidates.append(latest)

    for candidate in candidates:
        if _first(candidate, *_SCORE_KEYS) is not None:
            return candidate
    return None


def _format_change(today: float, previous: float) -> str | None:
    if previous == 0:
        return None
    change = round((today - previous) / previous * 100, 2)
    if change > 0:
        return f"+{change}% 📈"
    if change < 0:
        return f"{change}% 📉"
    return "0.0% ➖"


async def get_stock_feargreed(client: httpx.AsyncClient) -> dict | None:
    """
    Gets today's stock market Fear & Greed reading from feargreedmeter.com.

    Parameters
    ----------
    client : httpx.AsyncClient
        The HTTP client to use for the request.

    Returns
    -------
    dict | None
        ``{"value": int, "status": str, "change": str | None}``, or ``None``
        if the reading could not be fetched or parsed.
    """
    global _cache, _latest_cache

    if _cache is not None:
        ts, cached = _cache
        if time.time() - ts < _CACHE_TTL_SECONDS:
            return cached

    try:
        response = await client.get(_URL, headers=_HEADERS)
        response.raise_for_status()
        payload = response.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as e:
        logger.warning(f"Could not fetch stock Fear & Greed index: {e}")
        return _cache[1] if _cache is not None else None

    if not isinstance(payload, dict):
        logger.warning(f"Unexpected stock Fear & Greed payload type: {type(payload)}")
        return _cache[1] if _cache is not None else None

    summary = _find_summary(payload)
    if summary is None:
        logger.warning(f"Unexpected stock Fear & Greed payload shape: {payload!r}")
        return _cache[1] if _cache is not None else None

    score = _coerce_score(_first(summary, *_SCORE_KEYS))
    if score is None:
        return _cache[1] if _cache is not None else None

    rating = _first(summary, "rating", "label", "classification", "status")
    previous = _coerce_score(
        _first(summary, "previous_close", "previousClose", "prev_close")
    )

    result = {
        "value": round(score),
        "status": str(rating) if rating else _classify(score),
        "change": _format_change(score, previous) if previous is not None else None,
    }

    _cache = (time.time(), result)
    _latest_cache = summary
    return result


def _parse_cnn_history(payload: object, since: date) -> list[dict] | None:
    if not isinstance(payload, dict):
        return None
    historical = payload.get("fear_and_greed_historical")
    if not isinstance(historical, dict) or not isinstance(historical.get("data"), list):
        return None

    # Keyed by day so an intraday reading on the latest day replaces, rather
    # than duplicates, that day's close.
    by_day: dict[str, int] = {}
    for item in historical["data"]:
        if not isinstance(item, dict):
            continue
        x = _coerce_score(item.get("x"))
        y = _coerce_score(item.get("y"))
        if x is None or y is None:
            continue
        day = datetime.fromtimestamp(x / 1000, tz=timezone.utc).date()
        if day >= since:
            by_day[day.isoformat()] = round(y)

    if len(by_day) < 2:
        return None
    return [{"date": d, "value": v} for d, v in sorted(by_day.items())]


def _summary_history(summary: dict, days: int) -> list[dict] | None:
    """Sparse series from feargreedmeter's own week/month-ago readings."""
    try:
        today = date.fromisoformat(str(summary.get("date")))
    except ValueError:
        today = datetime.now(timezone.utc).date()

    offsets = [(1, "previous_close"), (0, "now")]
    if days >= 7:
        offsets.insert(0, (7, "one_week_ago"))
    if days >= 30:
        offsets.insert(0, (30, "one_month_ago"))

    points = []
    for offset, key in offsets:
        score = _coerce_score(summary.get(key))
        if score is not None:
            day = (today - timedelta(days=offset)).isoformat()
            points.append({"date": day, "value": round(score)})
    return points if len(points) >= 2 else None


async def get_stock_feargreed_history(
    client: httpx.AsyncClient, days: int
) -> dict | None:
    """
    Gets the stock market Fear & Greed index over the last ``days`` days.

    Daily readings come from CNN's graph data. If that is unavailable, the
    week/month-ago readings in the feargreedmeter.com summary are used as a
    sparse series instead.

    Parameters
    ----------
    client : httpx.AsyncClient
        The HTTP client to use for the request.
    days : int
        The size of the window, one of ``HISTORY_WINDOWS``.

    Returns
    -------
    dict | None
        ``{"days": int, "points": [{"date": str, "value": int}], "source": str}``
        oldest first, or ``None`` if neither source yields two readings.
    """
    cached = _history_cache.get(days)
    if cached is not None and time.time() - cached[0] < _HISTORY_CACHE_TTL_SECONDS:
        return cached[1]

    since = datetime.now(timezone.utc).date() - timedelta(days=days)
    points = None
    source = "cnn"
    try:
        response = await client.get(
            _HISTORY_URL.format(start=since.isoformat()), headers=_HISTORY_HEADERS
        )
        response.raise_for_status()
        points = _parse_cnn_history(response.json(), since)
        if points is None:
            logger.warning("Unexpected CNN Fear & Greed history payload shape")
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as e:
        logger.warning(f"Could not fetch stock Fear & Greed history: {e}")

    if points is None:
        await get_stock_feargreed(client)
        if _latest_cache is not None:
            points = _summary_history(_latest_cache, days)
            source = "feargreedmeter"

    if points is None:
        return cached[1] if cached is not None else None

    result = {"days": days, "points": points, "source": source}
    _history_cache[days] = (time.time(), result)
    return result
