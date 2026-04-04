import asyncio
import json
import logging
import os
import shutil
import subprocess
import time

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


if __name__ == "__main__":
    import asyncio

    async def main():
        async with httpx.AsyncClient() as client:
            data = await get_stocktwits_data(client, "ts")
            print(data)

    asyncio.run(main())
