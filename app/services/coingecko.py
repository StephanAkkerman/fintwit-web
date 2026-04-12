import asyncio
import logging
import time
from typing import Optional

import aiohttp

from .tradingview_quote import get_tradingview_quote
from .yahoo import get_stock_info

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.coingecko.com/api/v3/search"
_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"

_HEADERS = {
    "User-Agent": "fintwit-web/0.1 (+https://github.com/StephanAkkerman/fintwit-web)",
    "Accept": "application/json",
}

_CACHE_TTL_SECONDS = 120
_NEGATIVE_CACHE_TTL_SECONDS = 30

_cache: dict[str, tuple[float, Optional[dict]]] = {}
_coin_id_cache: dict[str, str] = {}
_cache_lock = asyncio.Lock()
_request_semaphore = asyncio.Semaphore(4)


def _pick_best_coin_id(coins: list[dict], ticker: str) -> str | None:
    ticker_lower = ticker.lower()

    for coin in coins:
        if str(coin.get("symbol") or "").lower() == ticker_lower:
            return str(coin.get("id") or "") or None

    for coin in coins:
        if str(coin.get("name") or "").lower() == ticker_lower:
            return str(coin.get("id") or "") or None

    first = coins[0] if coins else {}
    return str(first.get("id") or "") or None


async def _get_cached(ticker: str) -> tuple[bool, Optional[dict]]:
    async with _cache_lock:
        item = _cache.get(ticker)
        if item is None:
            return False, None

        ts, payload = item
        if time.time() - ts > _CACHE_TTL_SECONDS:
            _cache.pop(ticker, None)
            return False, None

        return True, payload


async def _set_cached(ticker: str, payload: Optional[dict]) -> None:
    async with _cache_lock:
        _cache[ticker] = (time.time(), payload)


async def _set_negative_cached(ticker: str) -> None:
    async with _cache_lock:
        # Keep a short negative cache to avoid tight retry loops when upstream is down.
        _cache[ticker] = (
            time.time() - (_CACHE_TTL_SECONDS - _NEGATIVE_CACHE_TTL_SECONDS),
            None,
        )


async def _resolve_coin_id(session: aiohttp.ClientSession, ticker: str) -> str | None:
    cached_coin_id = _coin_id_cache.get(ticker)
    if cached_coin_id:
        return cached_coin_id

    async with session.get(
        _SEARCH_URL,
        params={"query": ticker},
        headers=_HEADERS,
    ) as response:
        if response.status == 429:
            logger.warning("[coingecko] search rate-limited for %s", ticker)
            return None

        if response.status != 200:
            logger.debug("[coingecko] search status=%s for %s", response.status, ticker)
            return None

        data = await response.json()
        coins = data.get("coins", [])
        if not coins:
            return None

        coin_id = _pick_best_coin_id(coins, ticker)
        if coin_id:
            _coin_id_cache[ticker] = coin_id
        return coin_id


async def _fallback_to_yahoo(ticker: str) -> Optional[dict]:
    yahoo_symbol = f"{ticker}-USD"
    info = await get_stock_info(yahoo_symbol)
    if info is None:
        return None

    return {
        "price": info.get("price", 0.0),
        "change_percent": info.get("change_percent", 0.0),
        "volume": info.get("volume", 0.0),
        "website": info.get(
            "website", f"https://finance.yahoo.com/quote/{yahoo_symbol}"
        ),
        "source": info.get("source") or "yahoo",
    }


async def _fallback_to_tradingview(ticker: str) -> Optional[dict]:
    for candidate in (f"{ticker}USD", f"{ticker}-USD", ticker):
        payload = await get_tradingview_quote(candidate, asset_hint="crypto")
        if payload is not None:
            logger.info("[coingecko] using tradingview fallback for %s", ticker)
            return payload

    return None


async def _fallback_quote(ticker: str) -> Optional[dict]:
    yahoo_payload = await _fallback_to_yahoo(ticker)
    if yahoo_payload is not None:
        return yahoo_payload
    return await _fallback_to_tradingview(ticker)


def _reset_cache_for_tests() -> None:
    _cache.clear()
    _coin_id_cache.clear()


async def get_crypto_info(ticker: str) -> Optional[dict]:
    ticker = (ticker or "").upper()
    if not ticker:
        return None

    found, cached = await _get_cached(ticker)
    if found:
        return cached

    try:
        async with _request_semaphore:
            async with aiohttp.ClientSession() as session:
                coin_id = await _resolve_coin_id(session, ticker)
                if coin_id is None:
                    fallback = await _fallback_quote(ticker)
                    await _set_cached(ticker, fallback)
                    return fallback

                async with session.get(
                    _PRICE_URL,
                    params={
                        "ids": coin_id,
                        "vs_currencies": "usd",
                        "include_market_cap": "false",
                        "include_24hr_vol": "true",
                        "include_24hr_change": "true",
                        "include_last_updated_at": "false",
                    },
                    headers=_HEADERS,
                ) as price_response:
                    if price_response.status == 429:
                        logger.warning("[coingecko] price rate-limited for %s", ticker)
                        fallback = await _fallback_quote(ticker)
                        await _set_cached(ticker, fallback)
                        return fallback

                    if price_response.status != 200:
                        logger.debug(
                            "[coingecko] price status=%s for %s",
                            price_response.status,
                            ticker,
                        )
                        fallback = await _fallback_quote(ticker)
                        await _set_cached(ticker, fallback)
                        return fallback

                    price_data = await price_response.json()
                    if coin_id not in price_data:
                        fallback = await _fallback_quote(ticker)
                        await _set_cached(ticker, fallback)
                        return fallback

                    info = price_data[coin_id]
                    payload = {
                        "price": info.get("usd", 0.0),
                        "change_percent": info.get("usd_24h_change", 0.0),
                        "volume": info.get("usd_24h_vol", 0.0),
                        "website": f"https://www.coingecko.com/en/coins/{coin_id}",
                        "source": "coingecko",
                    }
                    await _set_cached(ticker, payload)
                    return payload
    except Exception as exc:
        logger.debug("[coingecko] %s fetch failed: %r", ticker, exc)
        fallback = await _fallback_quote(ticker)
        await _set_cached(ticker, fallback)
        return fallback

    await _set_negative_cached(ticker)
    return None


if __name__ == "__main__":
    import asyncio

    tickers = ["BTC", "ETH", "INVALID"]
    for ticker in tickers:
        info = asyncio.run(get_crypto_info(ticker))
        print(f"{ticker}: {info}")
