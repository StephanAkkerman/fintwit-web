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
