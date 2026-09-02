import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

VALID_KEYWORDS = {"ts", "m_day", "wl_ct_day"}
_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:149.0) Gecko/20100101 Firefox/149.0",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://stocktwits.com/",
}
_CACHE_TTL_SECONDS = 180
_CACHE: dict[str, tuple[float, list[dict]]] = {}


def _format_stocktwits_payload(payload: dict, keyword: str) -> list[dict]:
    if not payload or "table" not in payload or keyword not in payload["table"]:
        return []

    table_data = payload["table"][keyword]
    stocks_data = payload.get("stocks", {})

    merged_data = []
    for item in table_data:
        stock_id_str = str(item.get("stock_id", ""))
        stock_info = stocks_data.get(stock_id_str, {})

        # Merge table item and stock info
        merged_item = {**stock_info, **item}
        merged_data.append(merged_item)

    # Sort by 'val' descending
    merged_data.sort(key=lambda x: float(x.get("val", 0) or 0), reverse=True)

    formatted_data = []
    for item in merged_data:
        price = float(item.get("price") or 0)
        change = float(item.get("change") or 0)

        # Format % change
        if change > 0:
            change_str = f" (+{round(change, 2)}% 📈)"
        else:
            change_str = f" ({round(change, 2)}% 📉)"

        # Format price
        formatted_price = f"{round(price, 3)}{change_str}"

        formatted_data.append(
            {
                "stock_id": item.get("stock_id"),
                "symbol": str(item.get("symbol", "")),
                "name": str(item.get("name", "")),
                "price": formatted_price,
                "val": str(item.get("val", "")),
            }
        )

    return formatted_data


def _fetch_with_curl_sync(url: str) -> dict | None:
    candidates = [
        shutil.which("curl.exe"),
        shutil.which("curl"),
        r"C:\Windows\System32\curl.exe",
    ]
    curl_bin = next((c for c in candidates if c and os.path.exists(c)), None)
    if curl_bin is None:
        return None

    args = [
        curl_bin,
        "-sS",
        "--compressed",
        "-L",
        "--connect-timeout",
        "15",
        "--max-time",
        "25",
        "--retry",
        "2",
        "--retry-delay",
        "1",
        url,
    ]
    for key, value in _BROWSER_HEADERS.items():
        args.extend(["-H", f"{key}: {value}"])

    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
        )

        if proc.returncode != 0:
            logger.debug(
                "[stocktwits] curl failed: rc=%s err=%s",
                proc.returncode,
                (proc.stderr or "")[:200],
            )
            return None

        payload = json.loads(proc.stdout or "")
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("[stocktwits] curl fallback failed: %r", exc)
        return None


async def _fetch_with_curl(url: str) -> dict | None:
    return await asyncio.to_thread(_fetch_with_curl_sync, url)


def _get_cached(keyword: str) -> list[dict] | None:
    cached = _CACHE.get(keyword)
    if cached is None:
        return None

    ts, payload = cached
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _CACHE.pop(keyword, None)
        return None

    return payload


def _set_cached(keyword: str, payload: list[dict]) -> None:
    _CACHE[keyword] = (time.time(), payload)


async def get_stocktwits_data(
    client: httpx.AsyncClient, keyword: str
) -> list[dict] | None:
    """
    Gets the data from StockTwits based on the passed keywords.

    Parameters
    ----------
    client : httpx.AsyncClient
        The HTTP client to use for the request.
    keyword : str
        The specific keyword to get the data for. Options are: ts, m_day, wl_ct_day.

    Returns
    -------
    list[dict] | None
        A list of dictionaries representing the stocktwits rankings, or None if an error occurred.
    """
    if keyword not in VALID_KEYWORDS:
        logger.warning(f"Invalid keyword for StockTwits: {keyword}")
        return None

    url = f"https://api.stocktwits.com/api/2/charts/{keyword}"

    try:
        # Prefer curl first because StockTwits often blocks TLS fingerprints from Python clients.
        data = await _fetch_with_curl(url)
        response: httpx.Response | None = None

        if data is None:
            response = await client.get(
                url, headers=_BROWSER_HEADERS, follow_redirects=True
            )
            if response.status_code == 200:
                try:
                    json_payload = response.json()
                    if isinstance(json_payload, dict):
                        data = json_payload
                except ValueError:
                    data = None

        if data is None:
            cached = _get_cached(keyword)
            if cached is not None:
                logger.warning(
                    "[stocktwits] using cached data for keyword=%s",
                    keyword,
                )
                return cached

            status = (
                response.status_code if response is not None else "curl+httpx-failed"
            )
            logger.warning(
                "[stocktwits] unavailable keyword=%s status=%s",
                keyword,
                status,
            )
            return None

        formatted = _format_stocktwits_payload(data, keyword)
        _set_cached(keyword, formatted)
        return formatted
    except (
        httpx.RequestError,
        httpx.HTTPStatusError,
        ValueError,
        TypeError,
        KeyError,
    ) as e:
        logger.exception(f"Could not fetch or process data from StockTwits: {e}")
        return None


_SENTIMENT_CACHE_TTL_SECONDS = 180
_SENTIMENT_CACHE: dict[str, tuple[float, dict | None]] = {}


def _normalize_symbol(symbol: str) -> str:
    return (symbol or "").strip().upper()


def _coerce_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick(source: dict, *keys: str) -> object:
    for key in keys:
        if key in source and source[key] is not None:
            return source[key]
    return None


def _latest_sentiment_point(payload: dict) -> dict | None:
    """Return the most recent per-symbol datapoint from a sentiment-api payload.

    The `sentiment-api/v2/{symbol}/detail` endpoint's schema isn't publicly
    documented; it takes an `end` timestamp cursor (mirroring stocktwits.com's
    own sentiment-history chart), so this treats the payload as either a
    single snapshot or a time-ordered series and uses the newest entry either
    way.
    """
    if not isinstance(payload, dict):
        return None

    for list_key in ("data", "points", "results", "series", "history"):
        series = payload.get(list_key)
        if isinstance(series, list) and series:
            candidate = series[-1]
            if isinstance(candidate, dict):
                return candidate

    return payload


def _format_stocktwits_sentiment(payload: dict, symbol: str) -> dict | None:
    point = _latest_sentiment_point(payload)
    if not isinstance(point, dict):
        return None

    bullish = _coerce_float(
        _pick(point, "bullish_percent", "bullishPercent", "bullish", "pct_bullish")
    )
    bearish = _coerce_float(
        _pick(point, "bearish_percent", "bearishPercent", "bearish", "pct_bearish")
    )

    if bullish is None and bearish is None:
        bullish_count = _coerce_float(_pick(point, "bullish_count", "bullishCount"))
        bearish_count = _coerce_float(_pick(point, "bearish_count", "bearishCount"))
        if bullish_count is not None and bearish_count is not None:
            total = bullish_count + bearish_count
            if total > 0:
                bullish = round(bullish_count / total * 100, 2)
                bearish = round(bearish_count / total * 100, 2)

    if bullish is None and bearish is None:
        score = _coerce_float(
            _pick(point, "sentiment_score", "sentimentScore", "score")
        )
        if score is not None:
            # StockTwits sentiment scores run -100 (all bearish) .. +100 (all bullish).
            bullish = round((score + 100) / 2, 2)
            bearish = round(100 - bullish, 2)

    volume = _pick(point, "message_volume", "messageVolume", "volume", "total", "count")
    volume = int(volume) if isinstance(volume, (int, float)) else None

    as_of = _pick(point, "timestamp", "date", "end", "ts")
    as_of = str(as_of) if as_of is not None else None

    if bullish is None and bearish is None and volume is None:
        logger.debug(
            "[stocktwits] sentiment payload for %s had no recognizable fields: %s",
            symbol,
            list(point.keys()),
        )
        return None

    if bullish is not None and bearish is None:
        bearish = round(100 - bullish, 2)
    elif bearish is not None and bullish is None:
        bullish = round(100 - bearish, 2)

    return {
        "source": "stocktwits",
        "symbol": symbol,
        "bullish_percent": bullish,
        "bearish_percent": bearish,
        "message_volume": volume,
        "as_of": as_of,
        "website": f"https://stocktwits.com/symbol/{symbol}",
    }


def _get_cached_sentiment(symbol: str) -> dict | None:
    cached = _SENTIMENT_CACHE.get(symbol)
    if cached is None:
        return None

    ts, payload = cached
    if time.time() - ts > _SENTIMENT_CACHE_TTL_SECONDS:
        _SENTIMENT_CACHE.pop(symbol, None)
        return None

    return payload


def _set_cached_sentiment(symbol: str, payload: dict | None) -> None:
    _SENTIMENT_CACHE[symbol] = (time.time(), payload)


async def get_stocktwits_sentiment(symbol: str) -> dict | None:
    """
    Gets the community sentiment (Bullish/Bearish split) for a single ticker
    from StockTwits' sentiment-api, for attaching to enriched posts.

    Parameters
    ----------
    symbol : str
        The ticker to fetch sentiment for, e.g. "AAPL" or "VELO".

    Returns
    -------
    dict | None
        ``{"source", "symbol", "bullish_percent", "bearish_percent",
        "message_volume", "as_of", "website"}``, or ``None`` if the ticker is
        empty, the request fails, or the response carries no usable fields.
    """
    ticker = _normalize_symbol(symbol)
    if not ticker:
        return None

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    url = f"https://api-gw-prd.stocktwits.com/sentiment-api/v2/{ticker}/detail"

    try:
        # Prefer curl first, same as get_stocktwits_data: StockTwits often
        # blocks TLS fingerprints from Python HTTP clients.
        data = await _fetch_with_curl(f"{url}?end={now_iso}")
        response: httpx.Response | None = None

        if data is None:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    params={"end": now_iso},
                    headers=_BROWSER_HEADERS,
                    follow_redirects=True,
                )
            if response.status_code == 200:
                try:
                    json_payload = response.json()
                    if isinstance(json_payload, dict):
                        data = json_payload
                except ValueError:
                    data = None

        if data is None:
            cached = _get_cached_sentiment(ticker)
            if cached is not None:
                logger.warning(
                    "[stocktwits] using cached sentiment for symbol=%s", ticker
                )
                return cached

            status = (
                response.status_code if response is not None else "curl+httpx-failed"
            )
            logger.warning(
                "[stocktwits] sentiment unavailable symbol=%s status=%s",
                ticker,
                status,
            )
            return None

        formatted = _format_stocktwits_sentiment(data, ticker)
        _set_cached_sentiment(ticker, formatted)
        return formatted
    except (
        httpx.RequestError,
        httpx.HTTPStatusError,
        ValueError,
        TypeError,
        KeyError,
    ) as e:
        logger.exception(f"Could not fetch or process StockTwits sentiment: {e}")
        return None


if __name__ == "__main__":
    import asyncio

    async def main():
        async with httpx.AsyncClient() as client:
            data = await get_stocktwits_data(client, "ts")
            print(data)

        sentiment = await get_stocktwits_sentiment("AAPL")
        print(sentiment)

    asyncio.run(main())
