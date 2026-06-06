"""Market hours service using Yahoo Finance quote API."""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300

# (display_name, Yahoo Finance symbol)
_EXCHANGES: list[tuple[str, str]] = [
    ("NYSE", "SPY"),
    ("NASDAQ", "QQQ"),
    ("LSE", "^FTSE"),
    ("JPX", "^N225"),
    ("HKEX", "^HSI"),
]

_EXCHANGE_ORDER = [name for name, _ in _EXCHANGES]
_SYMBOLS = ",".join(sym for _, sym in _EXCHANGES)

_YAHOO_URL = "https://query1.finance.yahoo.com/v7/finance/quote"

# Map Yahoo's fullExchangeName to our display names.
_FULL_NAME_TO_EXCHANGE: dict[str, str] = {
    "NYSE Arca": "NYSE",
    "NYSE": "NYSE",
    "NasdaqGS": "NASDAQ",
    "NasdaqGM": "NASDAQ",
    "Nasdaq": "NASDAQ",
    "NASDAQ": "NASDAQ",
    "FTSE": "LSE",
    "LSE": "LSE",
    "London": "LSE",
    "Tokyo": "JPX",
    "OSE.Ax": "JPX",
    "HKSE": "HKEX",
    "Hong Kong": "HKEX",
}

_STATE_TO_SESSION: dict[str, str] = {
    "PRE": "Pre-market",
    "PREPRE": "Pre-market",
    "REGULAR": "Open",
    "POST": "After-hours",
    "POSTPOST": "After-hours",
}

_OPEN_STATES: frozenset[str] = frozenset({"PRE", "PREPRE", "REGULAR", "POST", "POSTPOST"})

_cache: tuple[float, list[dict]] | None = None


def _reset_cache_for_tests() -> None:
    global _cache
    _cache = None


def _build_row(exchange: str, item: dict) -> dict:
    market_state = item.get("marketState", "")
    reg_time = item.get("regularMarketTime")
    as_of = (
        datetime.fromtimestamp(reg_time, tz=timezone.utc).isoformat()
        if reg_time
        else datetime.now(timezone.utc).isoformat()
    )
    return {
        "exchange": exchange,
        "symbol": item.get("symbol", ""),
        "session": _STATE_TO_SESSION.get(market_state, "Closed"),
        "is_open": market_state in _OPEN_STATES,
        "market_state": market_state,
        "as_of": as_of,
        "timezone": item.get("exchangeTimezoneName", ""),
        "exchange_name": item.get("fullExchangeName", ""),
    }


def _build_unknown_row(exchange: str) -> dict:
    return {
        "exchange": exchange,
        "symbol": "",
        "session": "Unknown",
        "is_open": False,
        "market_state": "UNKNOWN",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "timezone": "",
        "exchange_name": "",
    }


async def get_stock_market_hours(
    client: Optional[httpx.AsyncClient] = None,
) -> Optional[list[dict]]:
    """Return current session state for major exchanges via Yahoo Finance.

    Accepts an optional httpx client; creates one internally when omitted.
    Results are cached for ``_CACHE_TTL_SECONDS`` seconds. Stale cache is
    returned on HTTP errors (rate-limit / server errors) so the UI degrades
    gracefully.
    """
    global _cache

    # Serve from cache while still fresh.
    if _cache is not None:
        ts, cached_rows = _cache
        if time.time() - ts < _CACHE_TTL_SECONDS:
            return cached_rows

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient()

    try:
        response = await client.get(
            _YAHOO_URL,
            params={"symbols": _SYMBOLS},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10.0,
        )

        if response.status_code != 200:
            # Return stale cache (any age) rather than None when available.
            return _cache[1] if _cache is not None else None

        payload = response.json()
        results = (payload.get("quoteResponse") or {}).get("result") or []

        by_exchange: dict[str, dict] = {}
        for item in results:
            exchange = _FULL_NAME_TO_EXCHANGE.get(item.get("fullExchangeName", ""))
            if exchange:
                by_exchange[exchange] = _build_row(exchange, item)

        rows = [
            by_exchange[ex] if ex in by_exchange else _build_unknown_row(ex)
            for ex in _EXCHANGE_ORDER
        ]

        _cache = (time.time(), rows)
        return rows

    except Exception as exc:
        logger.warning("[market_hours] request failed: %r", exc)
        return _cache[1] if _cache is not None else None
    finally:
        if own_client:
            await client.aclose()
