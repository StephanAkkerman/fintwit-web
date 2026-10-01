import asyncio
import logging
import time
from collections.abc import Iterable

import httpx

logger = logging.getLogger(__name__)

_NASDAQ_BASE = "https://api.nasdaq.com/api"
_NASDAQ_WEB_BASE = "https://www.nasdaq.com"
_DEFAULT_SYMBOLS = ("SPY", "QQQ", "AAPL", "TSLA", "NVDA", "AMZN", "MSFT", "META")
_ETF_SYMBOLS = {"SPY", "QQQ", "IWM", "DIA", "XLF", "XLK", "XLE"}
_CACHE_TTL_SECONDS = 180
_CACHE: dict[tuple[str, ...], tuple[float, dict]] = {}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/market-activity/options/most-active",
}


def _coerce_int(value: object) -> int:
    try:
        if value is None:
            return 0
        if isinstance(value, bool):
            return 0
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value).replace(",", "").strip()
        return int(float(text)) if text else 0
    except (ValueError, TypeError):
        return 0


def _coerce_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).replace(",", "").replace("+", "").strip()
        return float(text) if text else None
    except (ValueError, TypeError):
        return None


def _normalize_symbols(symbols: Iterable[str] | None) -> tuple[str, ...]:
    raw = list(symbols or _DEFAULT_SYMBOLS)
    out: list[str] = []
    for sym in raw:
        normalized = str(sym or "").strip().upper()
        if not normalized:
            continue
        if not normalized.isalnum() or len(normalized) > 10:
            continue
        if normalized not in out:
            out.append(normalized)
    return tuple(out[:12])


def _asset_class_for_symbol(symbol: str) -> str:
    return "etf" if symbol in _ETF_SYMBOLS else "stocks"


async def _fetch_symbol_overview(client: httpx.AsyncClient, symbol: str) -> dict | None:
    asset_class = _asset_class_for_symbol(symbol)
    url = f"{_NASDAQ_BASE}/quote/{symbol}/option-chain/most-active?assetclass={asset_class}"

    try:
        response = await client.get(url, headers=_HEADERS)
        if response.status_code != 200:
            logger.warning(
                "[options] Nasdaq request failed for %s: status=%s",
                symbol,
                response.status_code,
            )
            return None

        payload = response.json()
    except (httpx.RequestError, ValueError) as exc:
        logger.warning("[options] Nasdaq request failed for %s: %r", symbol, exc)
        return None

    if not isinstance(payload, dict):
        return None

    data = payload.get("data")
    if not isinstance(data, dict):
        return None

    # Outside market hours Nasdaq answers 200 with `"rows": null` (or tables
    # missing), which is "no activity", not a failed request.
    calls_rows = (data.get("tableDataCalls") or {}).get("tableData", {}).get("rows")
    puts_rows = (data.get("tableDataPuts") or {}).get("tableData", {}).get("rows")
    calls_rows = [] if calls_rows is None else calls_rows
    puts_rows = [] if puts_rows is None else puts_rows

    if not isinstance(calls_rows, list) or not isinstance(puts_rows, list):
        return None

    call_volume = sum(
        _coerce_int(row.get("volume")) for row in calls_rows if isinstance(row, dict)
    )
    put_volume = sum(
        _coerce_int(row.get("volume")) for row in puts_rows if isinstance(row, dict)
    )
    total_volume = call_volume + put_volume

    put_call_ratio = round(put_volume / call_volume, 4) if call_volume > 0 else None

    def top_contract(rows: list[dict], contract_type: str) -> dict | None:
        valid = [row for row in rows if isinstance(row, dict)]
        if not valid:
            return None

        best = max(valid, key=lambda row: _coerce_int(row.get("volume")))
        row_url = str(best.get("url") or "").strip()
        website = (
            f"{_NASDAQ_WEB_BASE}{row_url}"
            if row_url.startswith("/")
            else (row_url or None)
        )

        return {
            "symbol": symbol,
            "contract_type": contract_type,
            "expiry_date": str(best.get("expiryDate") or "").strip() or None,
            "strike": _coerce_float(best.get("strike")),
            "last": _coerce_float(best.get("last")),
            "change_percent": _coerce_float(best.get("pctChange")),
            "volume": _coerce_int(best.get("volume")),
            "open_interest": _coerce_int(best.get("openINT")),
            "website": website,
        }

    top_call = top_contract(calls_rows, "CALL")
    top_put = top_contract(puts_rows, "PUT")

    as_of = data.get("tableDataCalls", {}).get("tableData", {}).get("asOf") or data.get(
        "tableDataPuts", {}
    ).get("tableData", {}).get("asOf")

    contracts: list[dict] = []
    if top_call is not None:
        contracts.append(top_call)
    if top_put is not None:
        contracts.append(top_put)

    return {
        "symbol": symbol,
        "asset_class": asset_class.upper(),
        "as_of": as_of,
        "call_volume": call_volume,
        "put_volume": put_volume,
        "total_volume": total_volume,
        "put_call_ratio": put_call_ratio,
        "bullish_minus_bearish": call_volume - put_volume,
        "top_call": top_call,
        "top_put": top_put,
        "contracts": contracts,
    }


def _get_cached(symbols: tuple[str, ...]) -> dict | None:
    cached = _CACHE.get(symbols)
    if cached is None:
        return None

    ts, data = cached
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _CACHE.pop(symbols, None)
        return None

    return data


def _set_cached(symbols: tuple[str, ...], payload: dict) -> None:
    _CACHE[symbols] = (time.time(), payload)


def _reset_cache_for_tests() -> None:
    _CACHE.clear()


async def get_options_overview(
    client: httpx.AsyncClient, symbols: Iterable[str] | None = None
) -> dict | None:
    normalized_symbols = _normalize_symbols(symbols)
    if not normalized_symbols:
        normalized_symbols = _DEFAULT_SYMBOLS

    cached = _get_cached(normalized_symbols)
    if cached is not None:
        return cached

    tasks = [_fetch_symbol_overview(client, symbol) for symbol in normalized_symbols]
    rows = await asyncio.gather(*tasks, return_exceptions=True)

    symbol_overview: list[dict] = []
    for row in rows:
        if isinstance(row, BaseException):
            continue
        if isinstance(row, dict):
            symbol_overview.append(row)

    if not symbol_overview:
        return None

    total_calls = sum(item.get("call_volume", 0) for item in symbol_overview)
    total_puts = sum(item.get("put_volume", 0) for item in symbol_overview)
    total_volume = total_calls + total_puts

    market_put_call_ratio = (
        round(total_puts / total_calls, 4) if total_calls > 0 else None
    )

    most_active_contracts = sorted(
        [
            c
            for item in symbol_overview
            for c in item.get("contracts", [])
            if isinstance(c, dict)
        ],
        key=lambda c: c.get("volume", 0),
        reverse=True,
    )[:12]

    bullish = sorted(
        symbol_overview,
        key=lambda item: item.get("bullish_minus_bearish", 0),
        reverse=True,
    )[:5]
    bearish = sorted(
        symbol_overview,
        key=lambda item: item.get("bullish_minus_bearish", 0),
    )[:5]

    payload = {
        "symbols": symbol_overview,
        "totals": {
            "call_volume": total_calls,
            "put_volume": total_puts,
            "total_volume": total_volume,
            "put_call_ratio": market_put_call_ratio,
        },
        "bullish": [
            {
                "symbol": item.get("symbol"),
                "call_volume": item.get("call_volume"),
                "put_volume": item.get("put_volume"),
                "bullish_minus_bearish": item.get("bullish_minus_bearish"),
            }
            for item in bullish
        ],
        "bearish": [
            {
                "symbol": item.get("symbol"),
                "call_volume": item.get("call_volume"),
                "put_volume": item.get("put_volume"),
                "bullish_minus_bearish": item.get("bullish_minus_bearish"),
            }
            for item in bearish
        ],
        "most_active_contracts": most_active_contracts,
        "source": "nasdaq",
    }

    _set_cached(normalized_symbols, payload)
    return payload
