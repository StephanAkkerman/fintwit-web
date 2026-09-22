import asyncio
import logging
import math
import time

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 3600
_CACHE: dict[str, tuple[float, dict | None]] = {}


def _get_cached(symbol: str) -> tuple[bool, dict | None]:
    cached = _CACHE.get(symbol)
    if cached is None:
        return False, None

    ts, data = cached
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _CACHE.pop(symbol, None)
        return False, None

    return True, data


def _set_cached(symbol: str, payload: dict | None) -> None:
    _CACHE[symbol] = (time.time(), payload)


def _reset_cache_for_tests() -> None:
    _CACHE.clear()


def _clean_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _fetch_fundamentals_sync(symbol: str) -> dict | None:
    """Blocking yfinance call — always run this via asyncio.to_thread."""
    import yfinance as yf

    info = yf.Ticker(symbol).info
    if not info:
        return None

    payload: dict = {
        "market_cap": _clean_number(info.get("marketCap")),
        "forward_pe": _clean_number(info.get("forwardPE")),
        "trailing_pe": _clean_number(info.get("trailingPE")),
        "eps_forward": _clean_number(info.get("epsForward")),
        "eps_trailing": _clean_number(info.get("epsTrailingTwelveMonths")),
        "nav": _clean_number(info.get("navPrice")),
        "day_volume": _clean_number(
            info.get("volume") or info.get("regularMarketVolume")
        ),
        "avg_volume": _clean_number(
            info.get("averageDailyVolume3Month") or info.get("averageVolume")
        ),
        "avg_volume_10d": _clean_number(
            info.get("averageDailyVolume10Day") or info.get("averageVolume10days")
        ),
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    if not payload:
        return None

    currency = info.get("currency")
    if isinstance(currency, str) and currency.strip():
        payload["currency"] = currency.strip().upper()

    return payload


async def get_fundamentals(symbol: str) -> dict | None:
    """Fetch slow-moving valuation fundamentals from Yahoo Finance via yfinance.

    Covers market cap, forward/trailing P/E, forward/trailing EPS, NAV (funds
    and ETFs only), and volume (today's regular-session volume alongside the
    3-month/10-day averages). Cached per symbol for an hour — the valuation
    fields move slowly enough that a tight TTL would only add load without
    changing what is shown; today's volume rides along in the same cache, so
    it can lag up to an hour behind the live session rather than being exact
    to the minute.
    """
    normalized = (symbol or "").strip().upper()
    if not normalized:
        return None

    found, cached = _get_cached(normalized)
    if found:
        return cached

    try:
        data = await asyncio.to_thread(_fetch_fundamentals_sync, normalized)
    except Exception as exc:
        logger.warning(
            "[fundamentals] yfinance fetch failed for %s: %r", normalized, exc
        )
        return None

    _set_cached(normalized, data)
    return data
