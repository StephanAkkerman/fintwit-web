import asyncio
import logging
import time
from typing import Optional

from ticker_price_data import get_tradingview_quote

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300
_cache: tuple[float, Optional[dict]] | None = None
_cache_lock = asyncio.Lock()

BASE_CURRENCY = "USD"

# (currency code, display name, TradingView symbol for 1 USD -> that currency)
SUPPORTED_CURRENCIES: list[tuple[str, str, str]] = [
    ("EUR", "Euro", "FX_IDC:USDEUR"),
    ("GBP", "British Pound", "FX_IDC:USDGBP"),
    ("JPY", "Japanese Yen", "FX_IDC:USDJPY"),
    ("CHF", "Swiss Franc", "FX_IDC:USDCHF"),
    ("AUD", "Australian Dollar", "FX_IDC:USDAUD"),
    ("CAD", "Canadian Dollar", "FX_IDC:USDCAD"),
]


async def _fetch_rate(symbol: str) -> Optional[float]:
    try:
        quote = await get_tradingview_quote(symbol, asset_hint="forex")
    except Exception as exc:
        logger.debug("[fx_rates] quote failed for %s: %r", symbol, exc)
        return None
    if not isinstance(quote, dict):
        return None
    price = quote.get("price")
    if not isinstance(price, (int, float)):
        return None
    return float(price)


async def _build_rates() -> Optional[dict]:
    tasks = [_fetch_rate(symbol) for _, _, symbol in SUPPORTED_CURRENCIES]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    rates: dict[str, float] = {}
    for (code, _, _), result in zip(SUPPORTED_CURRENCIES, results):
        if isinstance(result, BaseException) or result is None:
            continue
        rates[code] = result

    if not rates:
        return None

    return {"base": BASE_CURRENCY, "rates": rates}


async def _get_cached() -> tuple[bool, Optional[dict]]:
    async with _cache_lock:
        if _cache is None:
            return False, None
        ts, payload = _cache
        if time.time() - ts > _CACHE_TTL_SECONDS:
            return False, None
        return True, dict(payload) if isinstance(payload, dict) else payload


async def _set_cached(payload: Optional[dict]) -> None:
    async with _cache_lock:
        global _cache
        _cache = (time.time(), dict(payload) if isinstance(payload, dict) else payload)


async def get_fx_rates() -> Optional[dict]:
    """USD exchange rates for the currencies the portfolio page can convert to.

    Returns ``{"base": "USD", "rates": {"EUR": 0.92, ...}}`` where each rate is
    the amount of that currency one USD buys, or ``None`` if no rate could be
    fetched at all.
    """
    found, cached = await _get_cached()
    if found:
        return cached

    payload = await _build_rates()
    await _set_cached(payload)
    return payload


def _reset_cache_for_tests() -> None:
    global _cache
    _cache = None
