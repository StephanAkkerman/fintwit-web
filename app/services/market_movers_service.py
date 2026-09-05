"""Market movers via TradingView Scanner API (pre-market and after-hours)."""

import asyncio
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
_SCANNER_URL = "https://scanner.tradingview.com/america/scan"
_CACHE_TTL = 300  # seconds
_cache: tuple[float, str, dict] | None = None
_lock = asyncio.Lock()


def _current_prefix() -> str:
    """Return 'postmarket' from 16:00 ET onward, else 'premarket'."""
    return "postmarket" if datetime.now(_ET).hour >= 16 else "premarket"


def _build_payload(prefix: str, sort_order: str) -> dict:
    return {
        "filter": [
            {"left": "market_cap_basic", "operation": "greater", "right": 100_000_000},
            {"left": f"{prefix}_volume", "operation": "greater", "right": 0},
            {"left": f"{prefix}_change", "operation": "nempty"},
        ],
        "columns": [
            "name",
            "description",
            "close",
            f"{prefix}_close",
            f"{prefix}_change",
            f"{prefix}_volume",
            "market_cap_basic",
        ],
        "sort": {"sortBy": f"{prefix}_change", "sortOrder": sort_order},
        "range": [0, 10],
    }


def _parse_rows(rows: list) -> list[dict]:
    result = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        d = item.get("d", [])
        if len(d) < 7:
            continue
        symbol = (item.get("s") or "").split(":")[-1]
        result.append(
            {
                "symbol": symbol,
                "name": str(d[1] or d[0] or symbol),
                "price": float(d[2] or 0),
                "extended_price": float(d[3] or 0),
                "change_pct": float(d[4] or 0),
                "volume": int(d[5] or 0),
                "market_cap": float(d[6] or 0),
            }
        )
    return result


async def _fetch_movers(prefix: str) -> tuple[list, list]:
    async def _post(session: aiohttp.ClientSession, payload: dict) -> list:
        async with session.post(
            _SCANNER_URL,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            r.raise_for_status()
            body = await r.json(content_type=None)
            return body.get("data") or []

    async with aiohttp.ClientSession() as session:
        gainers_raw, losers_raw = await asyncio.gather(
            _post(session, _build_payload(prefix, "desc")),
            _post(session, _build_payload(prefix, "asc")),
        )
    return _parse_rows(gainers_raw), _parse_rows(losers_raw)


async def get_market_movers() -> dict | None:
    global _cache
    async with _lock:
        prefix = _current_prefix()
        session_type = "after-hours" if prefix == "postmarket" else "pre-market"

        if _cache is not None:
            ts, cached_prefix, payload = _cache
            if cached_prefix == prefix and time.time() - ts < _CACHE_TTL:
                return payload

        try:
            gainers, losers = await _fetch_movers(prefix)
        except Exception:
            logger.exception("Failed to fetch market movers from TradingView scanner")
            if _cache is not None:
                _, _, stale_payload = _cache
                return {**stale_payload, "stale": True}
            return None

        payload = {
            "session_type": session_type,
            "gainers": gainers,
            "losers": losers,
            "stale": False,
        }
        _cache = (time.time(), prefix, payload)
        return payload


def _reset_cache_for_tests() -> None:
    global _cache
    _cache = None


# ---------------------------------------------------------------------------
# Multi-market regular-session movers: gainers / losers / most active / penny
# stocks, across several TradingView scanner regions (issue #79).
# ---------------------------------------------------------------------------

# Maps our market key -> (TradingView scanner path segment, market-cap column).
# Country equity scanners share the same column family; the crypto scanner
# uses `market_cap_calc` instead of `market_cap_basic`.
MARKETS: dict[str, tuple[str, str]] = {
    "usa": ("america", "market_cap_basic"),
    "uk": ("uk", "market_cap_basic"),
    "india": ("india", "market_cap_basic"),
    "australia": ("australia", "market_cap_basic"),
    "canada": ("canada", "market_cap_basic"),
    "crypto": ("crypto", "market_cap_calc"),
}

CATEGORIES: tuple[str, ...] = ("gainers", "losers", "most_active", "penny_stocks")

_MOVERS_MIN_CAP = 100_000_000
_PENNY_MAX_PRICE = 5.0
_MOVERS_RANGE = 25

_multi_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_multi_lock = asyncio.Lock()


def _build_movers_payload(market: str, category: str) -> dict:
    _, cap_column = MARKETS[market]

    filters: list[dict] = [
        {"left": "volume", "operation": "greater", "right": 0},
        {"left": "change", "operation": "nempty"},
    ]
    if category == "penny_stocks":
        filters.append(
            {"left": "close", "operation": "less", "right": _PENNY_MAX_PRICE}
        )
    else:
        filters.append(
            {"left": cap_column, "operation": "greater", "right": _MOVERS_MIN_CAP}
        )

    if category == "losers":
        sort_by, sort_order = "change", "asc"
    elif category in ("most_active", "penny_stocks"):
        sort_by, sort_order = "volume", "desc"
    else:  # gainers
        sort_by, sort_order = "change", "desc"

    return {
        "filter": filters,
        "columns": ["name", "description", "close", "change", "volume", cap_column],
        "sort": {"sortBy": sort_by, "sortOrder": sort_order},
        "range": [0, _MOVERS_RANGE],
    }


def _parse_movers_rows(rows: list) -> list[dict]:
    result = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        d = item.get("d", [])
        if len(d) < 6:
            continue
        symbol = (item.get("s") or "").split(":")[-1]
        result.append(
            {
                "symbol": symbol,
                "name": str(d[1] or d[0] or symbol),
                "price": float(d[2] or 0),
                "change_pct": float(d[3] or 0),
                "volume": int(d[4] or 0),
                "market_cap": float(d[5] or 0),
            }
        )
    return result


async def _fetch_movers_list(market: str, category: str) -> list[dict]:
    scanner_path, _ = MARKETS[market]
    payload = _build_movers_payload(market, category)

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"https://scanner.tradingview.com/{scanner_path}/scan",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            r.raise_for_status()
            body = await r.json(content_type=None)
            rows = body.get("data") or []

    return _parse_movers_rows(rows)


async def get_movers(market: str, category: str) -> list[dict] | None:
    """Top movers for `market` (see `MARKETS`) and `category` (see `CATEGORIES`).

    Cached per (market, category) pair for `_CACHE_TTL` seconds. Returns
    `None` if the scanner request fails and there is no warm cache to fall
    back on.
    """
    if market not in MARKETS or category not in CATEGORIES:
        raise ValueError(f"Unsupported market/category: {market}/{category}")

    key = (market, category)
    async with _multi_lock:
        cached = _multi_cache.get(key)
        if cached is not None and time.time() - cached[0] < _CACHE_TTL:
            return cached[1]

        try:
            movers = await _fetch_movers_list(market, category)
        except Exception:
            logger.exception(
                "Failed to fetch %s/%s movers from TradingView scanner",
                market,
                category,
            )
            return cached[1] if cached is not None else None

        _multi_cache[key] = (time.time(), movers)
        return movers


def _reset_multi_cache_for_tests() -> None:
    _multi_cache.clear()
