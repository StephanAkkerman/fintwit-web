import asyncio
import logging
import math
import time

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 180
_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}


def _get_cached(key: tuple[str, str]) -> dict | None:
    cached = _CACHE.get(key)
    if cached is None:
        return None

    ts, data = cached
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None

    return data


def _set_cached(key: tuple[str, str], payload: dict) -> None:
    _CACHE[key] = (time.time(), payload)


def _reset_cache_for_tests() -> None:
    _CACHE.clear()


def _clean_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _contract_rows(df, option_type: str) -> list[dict]:
    if df is None:
        return []

    rows = []
    for _, row in df.iterrows():
        rows.append(
            {
                "option_type": option_type,
                "strike": _clean_number(row.get("strike")),
                "bid": _clean_number(row.get("bid")),
                "ask": _clean_number(row.get("ask")),
                "last_price": _clean_number(row.get("lastPrice")),
                "volume": int(_clean_number(row.get("volume")) or 0),
                "open_interest": int(_clean_number(row.get("openInterest")) or 0),
                "implied_volatility": _clean_number(row.get("impliedVolatility")),
                "change_percent": _clean_number(row.get("percentChange")),
                "in_the_money": bool(row.get("inTheMoney")),
            }
        )
    return rows


def _fetch_chain_sync(symbol: str, expiration: str | None) -> dict | None:
    """Blocking yfinance call — always run this via asyncio.to_thread."""
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    try:
        calls, puts, underlying = ticker.option_chain(expiration)
    except ValueError:
        # Stale or unknown expiration from the caller — fall back to nearest.
        calls, puts, underlying = ticker.option_chain(None)

    if not underlying:
        return None

    expirations = list(ticker.options)
    if not expirations:
        return None

    target_expiration = expiration if expiration in expirations else expirations[0]

    contracts = sorted(
        _contract_rows(calls, "CALL") + _contract_rows(puts, "PUT"),
        key=lambda c: (c["strike"] or 0, c["option_type"]),
    )

    last_price = underlying.get("postMarketPrice", underlying.get("regularMarketPrice"))

    return {
        "underlying": {
            "name": underlying.get("longName"),
            "last_price": _clean_number(last_price),
            "change": _clean_number(underlying.get("regularMarketChange")),
            "change_percent": _clean_number(
                underlying.get("regularMarketChangePercent")
            ),
            "market_cap": _clean_number(underlying.get("marketCap")),
            "year_high": _clean_number(underlying.get("fiftyTwoWeekHigh")),
            "year_low": _clean_number(underlying.get("fiftyTwoWeekLow")),
            "volume": _clean_number(underlying.get("regularMarketVolume")),
        },
        "expirations": expirations,
        "expiration": target_expiration,
        "contracts": contracts,
    }


async def get_options_chain(symbol: str, expiration: str | None = None) -> dict | None:
    """Fetch a per-symbol options chain from Yahoo Finance via yfinance.

    The blocking yfinance/requests call runs in a worker thread
    (asyncio.to_thread) so it never blocks the event loop. Results are cached
    per (symbol, expiration) for a short TTL to absorb repeated widget polls.
    """
    normalized_symbol = (symbol or "").strip().upper()
    if not normalized_symbol:
        return None

    cache_key = (normalized_symbol, expiration or "")
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        data = await asyncio.to_thread(_fetch_chain_sync, normalized_symbol, expiration)
    except Exception as exc:
        logger.warning(
            "[options-chain] yfinance fetch failed for %s: %r", normalized_symbol, exc
        )
        return None

    if data is None:
        return None

    payload = {"symbol": normalized_symbol, **data, "source": "yfinance"}
    _set_cached(cache_key, payload)
    return payload
