import asyncio
import logging
import math
import time

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 3600
_CACHE: dict[str, tuple[float, dict | None]] = {}
_VALUATION_CACHE: dict[str, tuple[float, dict | None]] = {}


def _get_cached(symbol: str, cache: dict | None = None) -> tuple[bool, dict | None]:
    cache = _CACHE if cache is None else cache
    cached = cache.get(symbol)
    if cached is None:
        return False, None

    ts, data = cached
    if time.time() - ts > _CACHE_TTL_SECONDS:
        cache.pop(symbol, None)
        return False, None

    return True, data


def _set_cached(symbol: str, payload: dict | None, cache: dict | None = None) -> None:
    (_CACHE if cache is None else cache)[symbol] = (time.time(), payload)


def _reset_cache_for_tests() -> None:
    _CACHE.clear()
    _VALUATION_CACHE.clear()


def _clean_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _fetch_info_sync(symbol: str) -> dict:
    """Blocking yfinance call — always run this via asyncio.to_thread."""
    import yfinance as yf

    return yf.Ticker(symbol).info or {}


def _fetch_fundamentals_sync(symbol: str) -> dict | None:
    """Blocking yfinance call — always run this via asyncio.to_thread."""
    return _fundamentals_from_info(_fetch_info_sync(symbol))


def _fundamentals_from_info(info: dict) -> dict | None:
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


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _percent(value: object) -> float | None:
    """yfinance reports ratios as fractions (0.12); return percent (12.0)."""
    number = _clean_number(value)
    return None if number is None else round(number * 100, 2)


def _valuation_from_info(info: dict) -> dict | None:
    """Valuation, analyst consensus and short interest from a yfinance ``info``."""
    if not info:
        return None

    price = _clean_number(info.get("currentPrice") or info.get("regularMarketPrice"))
    target_mean = _clean_number(info.get("targetMeanPrice"))
    analysts = {
        "rating": _text(info.get("recommendationKey")),
        "rating_score": _clean_number(info.get("recommendationMean")),
        "analyst_count": _clean_number(info.get("numberOfAnalystOpinions")),
        "target_mean": target_mean,
        "target_median": _clean_number(info.get("targetMedianPrice")),
        "target_high": _clean_number(info.get("targetHighPrice")),
        "target_low": _clean_number(info.get("targetLowPrice")),
        "upside_percent": (
            round((target_mean / price - 1) * 100, 2) if target_mean and price else None
        ),
    }
    valuation = {
        "price": price,
        "price_to_book": _clean_number(info.get("priceToBook")),
        "price_to_sales": _clean_number(info.get("priceToSalesTrailing12Months")),
        "peg_ratio": _clean_number(
            info.get("trailingPegRatio") or info.get("pegRatio")
        ),
        "enterprise_to_ebitda": _clean_number(info.get("enterpriseToEbitda")),
        "revenue_growth_percent": _percent(info.get("revenueGrowth")),
        "earnings_growth_percent": _percent(info.get("earningsGrowth")),
        "profit_margin_percent": _percent(info.get("profitMargins")),
        "dividend_yield_percent": _clean_number(info.get("dividendYield")),
        "beta": _clean_number(info.get("beta")),
    }
    short_interest = {
        "short_percent_of_float": _percent(info.get("shortPercentOfFloat")),
        "short_ratio_days": _clean_number(info.get("shortRatio")),
        "shares_short": _clean_number(info.get("sharesShort")),
        "shares_short_prior_month": _clean_number(info.get("sharesShortPriorMonth")),
    }
    payload = {
        "name": _text(info.get("longName") or info.get("shortName")),
        "sector": _text(info.get("sector")),
        "industry": _text(info.get("industry")),
        "fundamentals": _fundamentals_from_info(info),
        "valuation": {k: v for k, v in valuation.items() if v is not None},
        "analysts": {k: v for k, v in analysts.items() if v is not None},
        "short_interest": {k: v for k, v in short_interest.items() if v is not None},
    }
    payload = {k: v for k, v in payload.items() if v}
    return payload or None


async def get_valuation(symbol: str) -> dict | None:
    """Valuation ratios, analyst targets and short interest for one symbol.

    Everything comes from one yfinance ``info`` lookup (cached for an hour),
    so it is a superset of :func:`get_fundamentals`. Funds and crypto have
    most fields missing; those are left out rather than returned as null.
    """
    normalized = (symbol or "").strip().upper()
    if not normalized:
        return None

    found, cached = _get_cached(normalized, _VALUATION_CACHE)
    if found:
        return cached

    try:
        info = await asyncio.to_thread(_fetch_info_sync, normalized)
    except Exception as exc:
        logger.warning("[valuation] yfinance fetch failed for %s: %r", normalized, exc)
        return None

    data = _valuation_from_info(info)
    if data is not None:
        data = {"symbol": normalized, **data}
    _set_cached(normalized, data, _VALUATION_CACHE)
    return data
