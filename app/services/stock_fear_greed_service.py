"""Stock market Fear & Greed Index client (feargreedmeter.com).

feargreedmeter.com is a CNN-style Fear & Greed Index clone; its backend at
``api2.mmeter.app`` is undocumented, so the payload shape below is inferred
rather than recorded from a verified response. ``_find_summary`` is
deliberately tolerant of a few plausible shapes (a flat top-level object, or
one nested under a ``fear_and_greed``/``stock``/``stocks`` key) and the
service returns ``None`` rather than raising if none of them match, so an
upstream schema change degrades to "unavailable" instead of a crash.
"""

import logging
import time

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

# (inclusive upper bound, label), standard 0-100 Fear & Greed scale.
_BUCKETS = (
    (25, "Extreme Fear"),
    (40, "Fear"),
    (60, "Neutral"),
    (75, "Greed"),
    (100, "Extreme Greed"),
)

_SUMMARY_KEYS = ("fear_and_greed", "stock", "stocks", "data", "summary", "result")


def _reset_cache_for_tests() -> None:
    global _cache
    _cache = None


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

    for candidate in candidates:
        if _first(candidate, "score", "value") is not None:
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
    global _cache

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

    score = _coerce_score(_first(summary, "score", "value"))
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
    return result
