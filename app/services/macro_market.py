import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from ticker_price_data import get_tradingview_quote

try:
    from .market_hours_service import get_stock_market_hours
except ImportError:  # pragma: no cover - allows direct script execution
    from app.services.market_hours_service import get_stock_market_hours

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300
_REQUEST_SEMAPHORE = asyncio.Semaphore(6)
_cache: tuple[float, Optional[dict]] | None = None
_cache_lock = asyncio.Lock()

YIELD_CURVES: dict[str, list[tuple[str, str]]] = {
    "US": [
        ("1M", "TVC:US01MY"),
        ("3M", "TVC:US03MY"),
        ("6M", "TVC:US06MY"),
        ("1Y", "TVC:US01Y"),
        ("2Y", "TVC:US02Y"),
        ("3Y", "TVC:US03Y"),
        ("5Y", "TVC:US05Y"),
        ("7Y", "TVC:US07Y"),
        ("10Y", "TVC:US10Y"),
        ("20Y", "TVC:US20Y"),
        ("30Y", "TVC:US30Y"),
    ],
    "EU": [
        ("3M", "TVC:EU03MY"),
        ("6M", "TVC:EU06MY"),
        ("9M", "TVC:EU09MY"),
        ("1Y", "TVC:EU01Y"),
        ("2Y", "TVC:EU02Y"),
        ("3Y", "TVC:EU03Y"),
        ("4Y", "TVC:EU04Y"),
        ("5Y", "TVC:EU05Y"),
        ("6Y", "TVC:EU06Y"),
        ("7Y", "TVC:EU07Y"),
        ("8Y", "TVC:EU08Y"),
        ("9Y", "TVC:EU09Y"),
        ("10Y", "TVC:EU10Y"),
        ("15Y", "TVC:EU15Y"),
        ("20Y", "TVC:EU20Y"),
        ("25Y", "TVC:EU25Y"),
        ("30Y", "TVC:EU30Y"),
    ],
}

FX_INDICES: list[tuple[str, str, str]] = [
    ("DXY", "US Dollar Index", "TVC:DXY"),
    ("EXY", "Euro Currency Index", "TVC:EXY"),
    ("BXY", "British Pound Index", "TVC:BXY"),
    ("JXY", "Japanese Yen Index", "TVC:JXY"),
]

CRYPTO_INDICES: list[tuple[str, str, str]] = [
    ("TOTAL", "Total Crypto Market Cap", "CRYPTOCAP:TOTAL"),
    ("TOTAL2", "Total Crypto Market Cap 2", "CRYPTOCAP:TOTAL2"),
    ("TOTAL3", "Total Crypto Market Cap 3", "CRYPTOCAP:TOTAL3"),
    ("BTC.D", "Bitcoin Dominance", "CRYPTOCAP:BTC.D"),
    ("ETH.D", "Ethereum Dominance", "CRYPTOCAP:ETH.D"),
    ("OTHERS.D", "Altcoin Dominance", "CRYPTOCAP:OTHERS.D"),
    ("TOTALDEFI.D", "DeFi Dominance", "CRYPTOCAP:TOTALDEFI.D"),
    ("USDT.D", "Tether Dominance", "CRYPTOCAP:USDT.D"),
    ("USDC.D", "USD Coin Dominance", "CRYPTOCAP:USDC.D"),
]

STOCK_INDICES: list[tuple[str, str, str]] = [
    ("SPY", "SPY", "AMEX:SPY"),
    ("NDX", "Nasdaq 100", "IG:NASDAQ"),
    ("PCC", "Put / Call Ratio", "USI:PCC"),
    ("PCCE", "Put / Call Ratio (Equities)", "USI:PCCE"),
    ("VIX", "Volatility Index S&P 500", "TVC:VIX"),
    ("SPX", "S&P 500", "TVC:SPX"),
]


def _normalize_symbol(symbol: str) -> str:
    value = (symbol or "").strip().upper()
    if not value:
        return ""
    if ":" in value:
        _, _, value = value.partition(":")
    return value


async def _quote(
    symbol: str, asset_hint: str, prefer_realtime: bool = True
) -> Optional[dict]:
    return await get_tradingview_quote(
        symbol, asset_hint=asset_hint, prefer_realtime=prefer_realtime
    )


async def _fetch_curve_points(label: str, bonds: list[tuple[str, str]]) -> dict:
    # Use scanner path for large curve batches to avoid starving the pooled websocket.
    tasks = [_quote(symbol, "index", prefer_realtime=False) for _, symbol in bonds]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    points: list[dict] = []
    for (maturity, symbol), result in zip(bonds, results):
        if isinstance(result, BaseException):
            logger.debug(
                "[macro] quote failed for %s (%s): %r", maturity, symbol, result
            )
            continue
        if not isinstance(result, dict):
            continue
        price = result.get("price")
        if not isinstance(price, (int, float)):
            continue

        points.append(
            {
                "maturity": maturity,
                "symbol": _normalize_symbol(symbol),
                "yield_percent": float(price),
                "change_percent": result.get("change_percent"),
                "website": result.get("website"),
                "source": result.get("source"),
            }
        )

    spread_2s10s = None
    ten_year = next((p for p in points if p["maturity"] == "10Y"), None)
    two_year = next((p for p in points if p["maturity"] == "2Y"), None)
    if ten_year and two_year:
        spread_2s10s = round(ten_year["yield_percent"] - two_year["yield_percent"], 4)

    return {
        "label": label,
        "points": points,
        "spread_2s10s": spread_2s10s,
    }


async def _fetch_fx_indices() -> list[dict]:
    async def _fetch_one(symbol: str, source_symbol: str) -> Optional[dict]:
        # Prefer full TradingView symbol first, then short alias fallback for compatibility.
        result = await _quote(source_symbol, "forex")
        if isinstance(result, dict):
            return result
        return await _quote(symbol, "forex")

    tasks = [
        _fetch_one(symbol, source_symbol) for symbol, _, source_symbol in FX_INDICES
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    rows: list[dict] = []
    for (symbol, name, _), result in zip(FX_INDICES, results):
        if isinstance(result, BaseException):
            logger.debug("[macro] quote failed for %s: %r", symbol, result)
            continue
        if not isinstance(result, dict):
            continue
        price = result.get("price")
        if not isinstance(price, (int, float)):
            continue

        rows.append(
            {
                "symbol": symbol,
                "name": name,
                "price": float(price),
                "change_percent": result.get("change_percent"),
                "website": result.get("website"),
                "source": result.get("source"),
            }
        )

    return rows


async def _fetch_indices(
    items: list[tuple[str, str, str]], asset_hint: str, category: str
) -> list[dict]:
    # Choose a more appropriate asset_hint per-item for indices that are real market indexes
    def _guess_hint(name: str, source_symbol: str, default: str) -> str:
        lname = (name or "").strip().lower()
        s = (source_symbol or "").upper()
        if (
            "nasdaq" in lname
            or "s&p" in lname
            or "vix" in lname
            or s.startswith("TVC:")
        ):
            return "index"
        return default

    if category == "stock":
        # Use sequential requests for stock panel symbols so the single websocket pool
        # has enough time to resolve each qualified symbol (e.g., USI:PCC, TVC:SPX).
        results: list[object] = []
        for _, name, source_symbol in items:
            try:
                result = await _quote(
                    source_symbol,
                    _guess_hint(name, source_symbol, asset_hint),
                    prefer_realtime=True,
                )
            except BaseException as exc:
                result = exc
            results.append(result)
    else:
        tasks = [
            _quote(
                source_symbol,
                _guess_hint(name, source_symbol, asset_hint),
                prefer_realtime=False,
            )
            for _, name, source_symbol in items
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    rows: list[dict] = []
    for (symbol, name, source_symbol), result in zip(items, results):
        if isinstance(result, BaseException):
            logger.debug("[macro] quote failed for %s: %r", symbol, result)
            continue
        if not isinstance(result, dict):
            continue
        price = result.get("price")
        if not isinstance(price, (int, float)):
            continue

        rows.append(
            {
                "symbol": symbol,
                "name": name,
                "price": float(price),
                "change_percent": result.get("change_percent"),
                "website": result.get("website"),
                "source": result.get("source"),
                "category": category,
                "tv_symbol": source_symbol,
            }
        )

    return rows


async def _should_show_stock_forex_indices() -> tuple[bool, list[dict]]:
    try:
        rows = await get_stock_market_hours()
    except Exception as exc:
        logger.debug("[macro] market hours lookup failed: %r", exc)
        return True, []

    visible = any(
        row.get("exchange") in {"NYSE", "NASDAQ"} and row.get("is_open") is True
        for row in rows
    )
    return visible, rows


async def _build_macro_snapshot() -> Optional[dict]:
    curves = await asyncio.gather(
        *[_fetch_curve_points(label, bonds) for label, bonds in YIELD_CURVES.items()],
        return_exceptions=True,
    )
    fx_indices = await _fetch_fx_indices()
    crypto_indices = await _fetch_indices(CRYPTO_INDICES, "crypto", "crypto")
    stock_indices = await _fetch_indices(STOCK_INDICES, "stock", "stock")
    stock_forex_visible, market_hours = await _should_show_stock_forex_indices()

    yield_curves = [
        curve for curve in curves if isinstance(curve, dict) and curve.get("points")
    ]
    if not yield_curves and not fx_indices and not crypto_indices and not stock_indices:
        return None

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "yield_curves": yield_curves,
        "crypto_indices": crypto_indices,
        "stock_forex_indices": stock_indices + fx_indices,
        "fx_indices": fx_indices,
        "stock_forex_visible": stock_forex_visible,
        "market_hours": market_hours,
        "sources": {
            "yield_curves": "tradingview",
            "crypto_indices": "tradingview",
            "stock_forex_indices": "tradingview",
            "fx_indices": "tradingview",
            "market_hours": "exchange_calendars",
        },
    }


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


async def get_macro_snapshot() -> Optional[dict]:
    found, cached = await _get_cached()
    if found:
        return cached

    async with _REQUEST_SEMAPHORE:
        found, cached = await _get_cached()
        if found:
            return cached

        payload = await _build_macro_snapshot()
        await _set_cached(payload)
        return payload


def _reset_cache_for_tests() -> None:
    global _cache
    _cache = None


if __name__ == "__main__":
    import asyncio as _asyncio
    import json

    async def main() -> None:
        snapshot = await get_macro_snapshot()
        print(json.dumps(snapshot, indent=2))

    _asyncio.run(main())
