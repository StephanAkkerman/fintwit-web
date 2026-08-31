"""Historical price series and all-time/52-week extreme statistics.

Backs the portfolio overview: the value-over-time chart needs aligned daily
closes per holding, and the per-asset highlights need to know how far an asset
sits from its all-time high/low and its 52-week range.

`ticker-price-data` only exposes live quotes, so history is fetched straight
from the Yahoo Finance chart endpoint here and cached in-process.
"""

import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36 Edg/110.0.1587.57"
    )
}

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_REQUEST_SEMAPHORE = asyncio.Semaphore(6)
_TIMEOUT_SECONDS = 12

# Series feeding the chart refresh often; the full history behind ATH/ATL
# barely moves, so it is cached far longer.
_SERIES_CACHE_TTL = 900  # 15 minutes
_STATS_CACHE_TTL = 3600  # 1 hour

_series_cache: dict[tuple[str, str], tuple[float, Optional[list[dict]]]] = {}
_stats_cache: dict[str, tuple[float, Optional[dict]]] = {}
_cache_lock = asyncio.Lock()

# Symbols Yahoo exposes under a different lookup name (mirrors ticker-price-data).
_SYMBOL_LOOKUP_OVERRIDES = {
    "DXY": "DX-Y.NYB",
    "VIX": "^VIX",
    "SPX": "^GSPC",
}

#: Supported chart ranges mapped to the Yahoo ``range``/``interval`` pair.
RANGE_PRESETS: dict[str, tuple[str, str]] = {
    "1W": ("5d", "1h"),
    "1M": ("1mo", "1d"),
    "3M": ("3mo", "1d"),
    "6M": ("6mo", "1d"),
    "YTD": ("ytd", "1d"),
    "1Y": ("1y", "1d"),
    "5Y": ("5y", "1wk"),
    "MAX": ("max", "1mo"),
}

DEFAULT_RANGE = "3M"

# Thresholds (percent) that decide which highlight flags an asset earns.
_AT_EXTREME_PCT = 0.5
_NEAR_EXTREME_PCT = 5.0
_NEAR_52W_PCT = 3.0
# Below this range width, "near the high/low" says nothing useful.
_MIN_RANGE_PCT = 10.0
_RECENT_DAYS = 30


def normalize_range(value: str | None) -> str:
    """Return a supported range key, falling back to :data:`DEFAULT_RANGE`.

    :param value: User-supplied range key (case-insensitive).
    :return: A key present in :data:`RANGE_PRESETS`.
    """
    key = (value or "").strip().upper()
    return key if key in RANGE_PRESETS else DEFAULT_RANGE


def _normalize_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper()


def _lookup_symbol(symbol: str) -> str:
    normalized = _normalize_symbol(symbol)
    return _SYMBOL_LOOKUP_OVERRIDES.get(normalized, normalized)


def _as_float(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None  # drop NaN


def _is_intraday(interval: str) -> bool:
    return interval.endswith(("m", "h"))


def _parse_chart(payload: dict, *, intraday: bool = False) -> Optional[list[dict]]:
    """Flatten a Yahoo chart response into ``{t, close, high, low}`` points.

    :param payload: Raw Yahoo chart JSON.
    :param intraday: When true, keep the full timestamp so sub-daily bars stay
        distinct instead of collapsing onto one date.
    """
    result = (payload.get("chart") or {}).get("result")
    if not result:
        return None

    chart = result[0]
    timestamps = chart.get("timestamp") or []
    quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []

    points: list[dict] = []
    for index, ts in enumerate(timestamps):
        close = _as_float(closes[index] if index < len(closes) else None)
        if close is None:
            continue

        moment = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        high = _as_float(highs[index] if index < len(highs) else None)
        low = _as_float(lows[index] if index < len(lows) else None)
        points.append(
            {
                "t": moment.isoformat() if intraday else moment.date().isoformat(),
                "close": close,
                "high": high if high is not None else close,
                "low": low if low is not None else close,
            }
        )

    return points or None


async def _fetch_chart(symbol: str, range_: str, interval: str) -> Optional[list[dict]]:
    url = _CHART_URL.format(symbol=_lookup_symbol(symbol))
    params = {"range": range_, "interval": interval}
    timeout = aiohttp.ClientTimeout(total=_TIMEOUT_SECONDS)

    async with _REQUEST_SEMAPHORE:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params, headers=_HEADERS) as resp:
                    if resp.status != 200:
                        logger.info(
                            "[price-history] %s %s returned HTTP %s",
                            symbol,
                            range_,
                            resp.status,
                        )
                        return None
                    payload = await resp.json(content_type=None)
        except Exception as exc:
            logger.debug("[price-history] %s %s fetch failed: %r", symbol, range_, exc)
            return None

    return _parse_chart(payload, intraday=_is_intraday(interval))


async def get_price_series(symbol: str, range_key: str = DEFAULT_RANGE) -> list[dict]:
    """Return daily ``{t, close, high, low}`` points for a symbol.

    :param symbol: Ticker symbol.
    :param range_key: Key from :data:`RANGE_PRESETS`.
    :return: Chronological points; empty when the symbol cannot be resolved.
    """
    normalized = _normalize_symbol(symbol)
    if not normalized:
        return []

    range_key = normalize_range(range_key)
    cache_key = (normalized, range_key)

    async with _cache_lock:
        cached = _series_cache.get(cache_key)
        if cached and time.time() - cached[0] <= _SERIES_CACHE_TTL:
            return list(cached[1] or [])

    range_, interval = RANGE_PRESETS[range_key]
    points = await _fetch_chart(normalized, range_, interval)

    async with _cache_lock:
        _series_cache[cache_key] = (time.time(), points)

    return list(points or [])


def _extreme(points: list[dict], field: str, pick_max: bool) -> Optional[dict]:
    best: Optional[dict] = None
    for point in points:
        value = point.get(field)
        if value is None:
            continue
        if best is None:
            best = {"value": value, "date": point["t"]}
            continue
        is_better = value > best["value"] if pick_max else value < best["value"]
        if is_better:
            best = {"value": value, "date": point["t"]}
    return best


def _pct_from(price: float, reference: Optional[dict]) -> Optional[float]:
    if not reference or not reference["value"]:
        return None
    return (price - reference["value"]) / reference["value"] * 100


def _days_since(reference: Optional[dict], today: date) -> Optional[int]:
    if not reference:
        return None
    try:
        return (today - date.fromisoformat(reference["date"])).days
    except ValueError:
        return None


def _build_flags(
    from_ath_pct: Optional[float],
    from_atl_pct: Optional[float],
    days_since_ath: Optional[int],
    days_since_atl: Optional[int],
    from_52w_high_pct: Optional[float],
    from_52w_low_pct: Optional[float],
    all_time_range_pct: Optional[float] = None,
    range_52w_width_pct: Optional[float] = None,
) -> list[dict]:
    """Turn raw distances into ordered, human-readable highlight flags.

    Two rules keep the output honest. A price is reported against at most one
    extreme — the nearer of the two — so nothing ever reads as both "at its
    all-time high" and "at its all-time low". And a range narrower than
    :data:`_MIN_RANGE_PCT` produces no proximity flags at all: on an instrument
    that barely moves, "near the high" says nothing.

    :param all_time_range_pct: Width of the all-time range, as a percentage of
        the all-time low.
    :param range_52w_width_pct: Width of the 52-week range, likewise.
    """
    flags: list[dict] = []

    def _too_tight(width: Optional[float]) -> bool:
        return width is not None and width < _MIN_RANGE_PCT

    at_ath = from_ath_pct is not None and from_ath_pct >= -_AT_EXTREME_PCT
    near_ath = from_ath_pct is not None and from_ath_pct >= -_NEAR_EXTREME_PCT
    at_atl = from_atl_pct is not None and from_atl_pct <= _AT_EXTREME_PCT
    near_atl = from_atl_pct is not None and from_atl_pct <= _NEAR_EXTREME_PCT

    if _too_tight(all_time_range_pct):
        at_ath = near_ath = at_atl = near_atl = False
    elif (
        (near_ath and near_atl)
        and from_ath_pct is not None
        and from_atl_pct is not None
    ):
        # Only reachable on a tight range; report whichever extreme is nearer.
        if abs(from_ath_pct) <= abs(from_atl_pct):
            at_atl = near_atl = False
        else:
            at_ath = near_ath = False

    if at_ath:
        flags.append({"code": "at_ath", "label": "All-time high", "tone": "bullish"})
    elif near_ath:
        flags.append(
            {
                "code": "near_ath",
                "label": f"{abs(from_ath_pct):.1f}% below ATH",
                "tone": "bullish",
            }
        )
    elif at_atl:
        flags.append({"code": "at_atl", "label": "All-time low", "tone": "bearish"})
    elif near_atl:
        flags.append(
            {
                "code": "near_atl",
                "label": f"{from_atl_pct:.1f}% above ATL",
                "tone": "bearish",
            }
        )

    # "Was recently there" — only worth saying when the price has since moved off
    # the extreme, so these are skipped whenever a proximity flag already fired.
    at_extreme = at_ath or near_ath or at_atl or near_atl
    if not at_extreme and not _too_tight(all_time_range_pct):
        if days_since_ath is not None and days_since_ath <= _RECENT_DAYS:
            flags.append(
                {
                    "code": "recent_ath",
                    "label": f"ATH {days_since_ath}d ago",
                    "tone": "neutral",
                }
            )
        if days_since_atl is not None and days_since_atl <= _RECENT_DAYS:
            flags.append(
                {
                    "code": "recent_atl",
                    "label": f"ATL {days_since_atl}d ago",
                    "tone": "neutral",
                }
            )

    # 52-week extremes only add information when no all-time extreme fired.
    if not at_extreme and not _too_tight(range_52w_width_pct):
        if from_52w_high_pct is not None and from_52w_high_pct >= -_NEAR_52W_PCT:
            flags.append(
                {
                    "code": "near_52w_high",
                    "label": "Near 52-week high",
                    "tone": "bullish",
                }
            )
        elif from_52w_low_pct is not None and from_52w_low_pct <= _NEAR_52W_PCT:
            flags.append(
                {"code": "near_52w_low", "label": "Near 52-week low", "tone": "bearish"}
            )

    return flags


async def get_symbol_stats(symbol: str, price: float | None = None) -> Optional[dict]:
    """Return ATH/ATL and 52-week statistics for a symbol.

    :param symbol: Ticker symbol.
    :param price: Live price to measure against. Defaults to the latest close in
        the historical series.
    :return: Stats dict, or ``None`` when no history could be fetched.
    """
    normalized = _normalize_symbol(symbol)
    if not normalized:
        return None

    async with _cache_lock:
        cached = _stats_cache.get(normalized)
        if cached and time.time() - cached[0] <= _STATS_CACHE_TTL:
            base = cached[1]
            return _apply_price(base, price) if base else None

    points = await _fetch_chart(normalized, "max", "1d")
    base = _compute_stats(normalized, points) if points else None

    async with _cache_lock:
        _stats_cache[normalized] = (time.time(), base)

    return _apply_price(base, price) if base else None


def _compute_stats(symbol: str, points: list[dict]) -> Optional[dict]:
    """Compute the price-independent part of a symbol's statistics."""
    if not points:
        return None

    today = datetime.now(timezone.utc).date()
    cutoff = (today - timedelta(days=365)).isoformat()
    last_year = [p for p in points if p["t"] >= cutoff] or points[-1:]

    return {
        "symbol": symbol,
        "last_close": points[-1]["close"],
        "history_start": points[0]["t"],
        "all_time_high": _extreme(points, "high", pick_max=True),
        "all_time_low": _extreme(points, "low", pick_max=False),
        "week_52_high": _extreme(last_year, "high", pick_max=True),
        "week_52_low": _extreme(last_year, "low", pick_max=False),
    }


def _apply_price(base: dict, price: float | None) -> dict:
    """Overlay live-price-dependent distances onto cached extremes."""
    reference = price if price is not None else base.get("last_close")
    stats = {**base, "price": reference}

    if reference is None:
        stats.update(
            {
                "from_ath_percent": None,
                "from_atl_percent": None,
                "from_52w_high_percent": None,
                "from_52w_low_percent": None,
                "range_position_52w": None,
                "days_since_ath": None,
                "days_since_atl": None,
                "flags": [],
            }
        )
        return stats

    today = datetime.now(timezone.utc).date()
    from_ath = _pct_from(reference, base.get("all_time_high"))
    from_atl = _pct_from(reference, base.get("all_time_low"))
    from_52w_high = _pct_from(reference, base.get("week_52_high"))
    from_52w_low = _pct_from(reference, base.get("week_52_low"))

    high_52w = (base.get("week_52_high") or {}).get("value")
    low_52w = (base.get("week_52_low") or {}).get("value")
    range_position = None
    range_width_pct = None
    if high_52w is not None and low_52w is not None and high_52w > low_52w:
        range_position = (reference - low_52w) / (high_52w - low_52w) * 100
        range_position = max(0.0, min(100.0, range_position))
        if low_52w:
            range_width_pct = (high_52w - low_52w) / low_52w * 100

    ath = (base.get("all_time_high") or {}).get("value")
    atl = (base.get("all_time_low") or {}).get("value")
    all_time_range_pct = (ath - atl) / atl * 100 if ath and atl else None

    days_since_ath = _days_since(base.get("all_time_high"), today)
    days_since_atl = _days_since(base.get("all_time_low"), today)

    stats.update(
        {
            "from_ath_percent": from_ath,
            "from_atl_percent": from_atl,
            "from_52w_high_percent": from_52w_high,
            "from_52w_low_percent": from_52w_low,
            "range_position_52w": range_position,
            "days_since_ath": days_since_ath,
            "days_since_atl": days_since_atl,
            "flags": _build_flags(
                from_ath,
                from_atl,
                days_since_ath,
                days_since_atl,
                from_52w_high,
                from_52w_low,
                all_time_range_pct,
                range_width_pct,
            ),
        }
    )
    return stats


def _reset_cache_for_tests() -> None:
    _series_cache.clear()
    _stats_cache.clear()
