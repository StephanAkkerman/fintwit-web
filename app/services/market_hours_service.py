import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"

_CACHE_TTL_SECONDS = 60
_STALE_CACHE_TTL_SECONDS = 900

_cache_lock = asyncio.Lock()
_fetch_lock = asyncio.Lock()
_cache_item: tuple[float, list[dict]] | None = None

_EXCHANGE_SYMBOLS = [
    ("NYSE", "SPY"),
    ("NASDAQ", "QQQ"),
    ("LSE", "^FTSE"),
    ("JPX", "^N225"),
    ("HKEX", "^HSI"),
]


def _clone_rows(rows: list[dict]) -> list[dict]:
    return [dict(row) for row in rows]


async def _get_cached(*, allow_stale: bool) -> list[dict] | None:
    global _cache_item

    async with _cache_lock:
        if _cache_item is None:
            return None

        ts, payload = _cache_item
        age = time.time() - ts

        if age <= _CACHE_TTL_SECONDS:
            return _clone_rows(payload)

        if allow_stale and age <= _STALE_CACHE_TTL_SECONDS:
            return _clone_rows(payload)

        if age > _STALE_CACHE_TTL_SECONDS:
            # Drop very old data so we don't serve stale sessions forever.
            _cache_item = None

        return None


async def _set_cached(payload: list[dict]) -> None:
    global _cache_item

    async with _cache_lock:
        _cache_item = (time.time(), _clone_rows(payload))


def _reset_cache_for_tests() -> None:
    global _cache_item
    _cache_item = None


def _to_session_label(market_state: str) -> tuple[str, bool]:
    state = (market_state or "").upper()

    if state in {"REGULAR", "OPEN"}:
        return "Open", True

    if state.startswith("PRE"):
        return "Pre-market", True

    if state.startswith("POST"):
        return "After-hours", True

    if state in {"CLOSED", "CLOSE"}:
        return "Closed", False

    if state:
        return state.replace("_", " ").title(), False

    return "Unknown", False


def _to_iso_utc(value: object) -> str | None:
    if not isinstance(value, (int, float)):
        return None

    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return None


async def get_stock_market_hours(client: httpx.AsyncClient) -> Optional[list[dict]]:
    """Return current market sessions for major exchanges via Yahoo quote marketState."""
    cached = await _get_cached(allow_stale=False)
    if cached is not None:
        return cached

    symbols = ",".join(symbol for _, symbol in _EXCHANGE_SYMBOLS)

    async with _fetch_lock:
        # Recheck cache after waiting for the fetch lock.
        cached = await _get_cached(allow_stale=False)
        if cached is not None:
            return cached

        try:
            response = await client.get(_YAHOO_QUOTE_URL, params={"symbols": symbols})
            if response.status_code != 200:
                stale = await _get_cached(allow_stale=True)
                if stale is not None:
                    if response.status_code == 429:
                        logger.info(
                            "Market-hours upstream rate-limited (429); serving stale cache"
                        )
                    else:
                        logger.warning(
                            "Market-hours upstream status=%s; serving stale cache",
                            response.status_code,
                        )
                    return stale

                logger.warning(
                    "Could not fetch stock market hours: status=%s",
                    response.status_code,
                )
                return None

            payload = response.json()
        except (httpx.RequestError, ValueError) as exc:
            logger.warning("Could not fetch stock market hours: %s", exc)
            stale = await _get_cached(allow_stale=True)
            if stale is not None:
                logger.info(
                    "Serving stale stock market hours cache after request error"
                )
                return stale
            return None

        rows = payload.get("quoteResponse", {}).get("result", [])
        by_symbol = {
            str(row.get("symbol") or "").upper(): row
            for row in rows
            if isinstance(row, dict)
        }

        results: list[dict] = []
        for exchange_name, symbol in _EXCHANGE_SYMBOLS:
            row = by_symbol.get(symbol.upper(), {})

            market_state = str(row.get("marketState") or "")
            session_label, is_open = _to_session_label(market_state)

            results.append(
                {
                    "exchange": exchange_name,
                    "symbol": symbol,
                    "session": session_label,
                    "is_open": is_open,
                    "market_state": market_state or None,
                    "as_of": _to_iso_utc(row.get("regularMarketTime")),
                    "timezone": row.get("exchangeTimezoneName"),
                    "exchange_name": row.get("fullExchangeName") or None,
                }
            )

        await _set_cached(results)
        return results


if __name__ == "__main__":

    async def main():
        async with httpx.AsyncClient() as client:
            hours = await get_stock_market_hours(client)
            print(hours)

    asyncio.run(main())
