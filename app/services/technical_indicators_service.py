"""Daily technical indicators for any ticker, read from TradingView's scanner.

TradingView already computes the standard indicators for every symbol it
lists, so nothing is calculated here: one Scanner request (the same public
endpoint ``market_breadth_service`` uses) returns them for a whole batch of
symbols. That keeps a holdings check to a single request and avoids pulling
and crunching a year of price history per symbol.

What comes back is the set a buy/sell check actually leans on:

- **RSI(14)**, daily and 4-hour: overbought above 70, oversold below 30.
- **MACD(12, 26, 9)**: which side of its signal line it is on, and whether
  it crossed on the latest bar.
- **Distance from the 20/50/200-day SMAs**, and the 50-vs-200 state (golden or
  death cross), flagging a cross that happened on the latest bar.
- **ATR(14)**, in price and as a percent of price: the typical daily range,
  for sizing a stop.
- **ADX(14)** with +DI/-DI: how strong the trend is and which way it points.
- **Volume** against its 30-day average (today's volume is partial until the
  close).
- TradingView's own **ratings** (all, moving averages, oscillators), daily and
  4-hour.

Stocks and ETFs are matched by name on the ``america`` scanner, preferring the
primary listing; crypto is looked up as a USD(T) pair on a few large spot
exchanges. The scanner's US data is delayed by 15 minutes.
"""

from __future__ import annotations

import asyncio
import logging
import time

import aiohttp

logger = logging.getLogger(__name__)

_SCANNER_URL = "https://scanner.tradingview.com/{market}/scan"
_CACHE_TTL = 300  # seconds
_TIMEOUT = aiohttp.ClientTimeout(total=15)
#: Most symbols one request (and one API call) may ask for.
MAX_SYMBOLS = 50

#: Crypto pairs to try, best first: the first one the scanner knows wins.
_CRYPTO_PAIRS = [
    ("BINANCE", "USDT"),
    ("COINBASE", "USD"),
    ("BYBIT", "USDT"),
    ("OKX", "USDT"),
    ("KRAKEN", "USD"),
]

_COLUMNS = [
    "name",
    "exchange",
    "type",
    "subtype",
    "is_primary",
    "close",
    "RSI",
    "RSI|240",
    "MACD.macd",
    "MACD.signal",
    "MACD.macd[1]",
    "MACD.signal[1]",
    "SMA20",
    "SMA50",
    "SMA200",
    "SMA50[1]",
    "SMA200[1]",
    "ATR",
    "ADX",
    "ADX+DI",
    "ADX-DI",
    "volume",
    "average_volume_30d_calc",
    "Recommend.All",
    "Recommend.MA",
    "Recommend.Other",
    "Recommend.All|240",
]

RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
#: ADX at or above this is a trending market; below ``_ADX_WEAK`` a range.
_ADX_STRONG = 25.0
_ADX_WEAK = 20.0
#: Volume this many times its 30-day average counts as heavy.
_HEAVY_VOLUME = 1.5

_cache: dict[tuple[str, str], tuple[float, dict | None]] = {}


def _reset_cache_for_tests() -> None:
    _cache.clear()


def _num(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None  # drop NaN


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def _pct_from(price: float | None, level: float | None) -> float | None:
    if price is None or not level:
        return None
    return round((price / level - 1) * 100, 2)


def rating_label(score: float | None) -> str | None:
    """TradingView's -1..1 rating score as the label its widgets show."""
    if score is None:
        return None
    if score >= 0.5:
        return "Strong Buy"
    if score >= 0.1:
        return "Buy"
    if score > -0.1:
        return "Neutral"
    if score > -0.5:
        return "Sell"
    return "Strong Sell"


def _cross(
    fast: float | None,
    slow: float | None,
    fast_prev: float | None,
    slow_prev: float | None,
) -> str | None:
    """``"up"`` or ``"down"`` when ``fast`` crossed ``slow`` on the last bar."""
    if None in (fast, slow, fast_prev, slow_prev):
        return None
    if fast_prev <= slow_prev and fast > slow:
        return "up"
    if fast_prev >= slow_prev and fast < slow:
        return "down"
    return None


def normalize_symbol(symbol: str, asset_kind: str) -> str:
    """Map the dashboard's spellings (``$BRK-B``, ``BTC-USD``) to a base name."""
    value = (symbol or "").strip().upper().lstrip("$")
    if ":" in value:
        value = value.split(":", 1)[1]
    if asset_kind == "crypto":
        value = value.replace("-", "").replace("/", "")
        for quote in ("USDT", "USDC", "USD"):
            if value.endswith(quote) and len(value) > len(quote):
                return value[: -len(quote)]
        return value
    # Yahoo writes share classes as BRK-B, TradingView as BRK.B.
    return value.replace("-", ".")


def parse_row(row: dict, symbol: str) -> dict | None:
    """Turn one scanner row (``{"s": ..., "d": [...]}``) into the indicator set."""
    values = row.get("d") if isinstance(row, dict) else None
    if not isinstance(values, list) or len(values) < len(_COLUMNS):
        return None
    f = dict(zip(_COLUMNS, values))
    price = _num(f["close"])
    if price is None:
        return None

    rsi = _num(f["RSI"])
    rsi_state = None
    if rsi is not None:
        rsi_state = (
            "overbought"
            if rsi >= RSI_OVERBOUGHT
            else "oversold"
            if rsi <= RSI_OVERSOLD
            else "neutral"
        )

    macd, signal = _num(f["MACD.macd"]), _num(f["MACD.signal"])
    macd_cross = _cross(
        macd, signal, _num(f["MACD.macd[1]"]), _num(f["MACD.signal[1]"])
    )

    sma50, sma200 = _num(f["SMA50"]), _num(f["SMA200"])
    ma_cross = _cross(sma50, sma200, _num(f["SMA50[1]"]), _num(f["SMA200[1]"]))
    ma_state = None
    if sma50 is not None and sma200 is not None:
        ma_state = "golden_cross" if sma50 > sma200 else "death_cross"

    atr = _num(f["ATR"])
    adx, plus_di, minus_di = _num(f["ADX"]), _num(f["ADX+DI"]), _num(f["ADX-DI"])
    strength = None
    if adx is not None:
        strength = (
            "strong"
            if adx >= _ADX_STRONG
            else "weak"
            if adx < _ADX_WEAK
            else "moderate"
        )
    direction = None
    if plus_di is not None and minus_di is not None:
        direction = "up" if plus_di > minus_di else "down"

    volume, avg_volume = _num(f["volume"]), _num(f["average_volume_30d_calc"])
    vs_avg = (
        round(volume / avg_volume, 2) if volume is not None and avg_volume else None
    )

    sma = {"sma20": _num(f["SMA20"]), "sma50": sma50, "sma200": sma200}
    result = {
        "symbol": symbol,
        "tv_symbol": str(row.get("s") or ""),
        "type": f["subtype"] or f["type"] or None,
        "price": price,
        "rsi": {
            "value": _round(rsi, 1),
            "state": rsi_state,
            "four_h": _round(_num(f["RSI|240"]), 1),
        },
        "macd": {
            "macd": _round(macd, 4),
            "signal": _round(signal, 4),
            "histogram": _round(
                macd - signal if macd is not None and signal is not None else None,
                4,
            ),
            "above_signal": None if None in (macd, signal) else macd > signal,
            "cross": {"up": "bullish", "down": "bearish"}.get(macd_cross or ""),
        },
        "moving_averages": {
            **{key: _round(value, 4) for key, value in sma.items()},
            **{
                f"price_vs_{key}_percent": _pct_from(price, value)
                for key, value in sma.items()
            },
            "sma50_vs_sma200": ma_state,
            "cross_today": {"up": "golden_cross", "down": "death_cross"}.get(
                ma_cross or ""
            ),
        },
        "atr": {
            "value": _round(atr, 4),
            "percent_of_price": _round(atr / price * 100 if atr else None),
        },
        "adx": {
            "value": _round(adx, 1),
            "trend_strength": strength,
            "direction": direction,
        },
        "volume": {
            "today": volume,
            "avg_30d": _round(avg_volume, 0),
            "vs_avg_30d": vs_avg,
        },
        "rating": {
            "one_d": rating_label(_num(f["Recommend.All"])),
            "four_h": rating_label(_num(f["Recommend.All|240"])),
            "moving_averages": rating_label(_num(f["Recommend.MA"])),
            "oscillators": rating_label(_num(f["Recommend.Other"])),
        },
    }
    result["signals"] = _signals(result)
    return result


def _signals(ind: dict) -> list[str]:
    """Short flags for the noteworthy readings, so a reader can skim them."""
    flags: list[str] = []
    if ind["rsi"]["state"] in ("overbought", "oversold"):
        flags.append(f"rsi_{ind['rsi']['state']}")
    if ind["macd"]["cross"]:
        flags.append(f"macd_{ind['macd']['cross']}_cross")
    ma = ind["moving_averages"]
    if ma["cross_today"]:
        flags.append(ma["cross_today"])
    vs200 = ma["price_vs_sma200_percent"]
    if vs200 is not None:
        flags.append("above_sma200" if vs200 >= 0 else "below_sma200")
    if ind["adx"]["trend_strength"] == "strong" and ind["adx"]["direction"]:
        flags.append(f"strong_{ind['adx']['direction']}trend")
    vs_avg = ind["volume"]["vs_avg_30d"]
    if vs_avg is not None and vs_avg >= _HEAVY_VOLUME:
        flags.append("heavy_volume")
    return flags


def _pick_listing(rows: list[dict]) -> dict | None:
    """Among same-named US listings, the primary one, then the most traded."""

    def key(row: dict) -> tuple[bool, float]:
        values = dict(zip(_COLUMNS, row.get("d") or []))
        return bool(values.get("is_primary")), _num(values.get("volume")) or 0.0

    return max(rows, key=key) if rows else None


async def _scan(
    session: aiohttp.ClientSession, market: str, payload: dict
) -> list[dict] | None:
    url = _SCANNER_URL.format(market=market)
    try:
        async with session.post(url, json=payload, timeout=_TIMEOUT) as resp:
            if resp.status != 200:
                logger.warning(
                    "[indicators] %s scanner returned status=%s", market, resp.status
                )
                return None
            body = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        logger.warning("[indicators] %s scanner request failed: %r", market, exc)
        return None
    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, list) else None


async def _fetch_us(
    session: aiohttp.ClientSession, names: list[str]
) -> dict[str, dict | None] | None:
    rows = await _scan(
        session,
        "america",
        {
            "filter": [{"left": "name", "operation": "in_range", "right": names}],
            "columns": _COLUMNS,
            "range": [0, len(names) * 5],
        },
    )
    if rows is None:
        return None
    by_name: dict[str, list[dict]] = {}
    for row in rows:
        values = row.get("d") if isinstance(row, dict) else None
        if isinstance(values, list) and values:
            by_name.setdefault(str(values[0]).upper(), []).append(row)
    result: dict[str, dict | None] = {}
    for name in names:
        best = _pick_listing(by_name.get(name, []))
        result[name] = parse_row(best, name) if best else None
    return result


async def _fetch_crypto(
    session: aiohttp.ClientSession, bases: list[str]
) -> dict[str, dict | None] | None:
    tickers = [
        f"{exchange}:{base}{quote}"
        for base in bases
        for exchange, quote in _CRYPTO_PAIRS
    ]
    rows = await _scan(
        session, "crypto", {"symbols": {"tickers": tickers}, "columns": _COLUMNS}
    )
    if rows is None:
        return None
    by_ticker = {str(row.get("s")): row for row in rows if isinstance(row, dict)}
    result: dict[str, dict | None] = {}
    for base in bases:
        result[base] = None
        for exchange, quote in _CRYPTO_PAIRS:
            row = by_ticker.get(f"{exchange}:{base}{quote}")
            parsed = parse_row(row, base) if row else None
            if parsed is not None:
                result[base] = parsed
                break
    return result


async def get_indicators(
    symbols: list[str], asset_kind: str = "stock"
) -> dict[str, dict | None]:
    """Indicators per requested symbol (``None`` where TradingView has none).

    Keys are the symbols as passed in, upper-cased. ``asset_kind`` is
    ``stock`` or ``etf`` (both on the US scanner) or ``crypto``; anything else
    returns ``None`` for every symbol. A failed scanner request is not cached,
    so the next call retries it.
    """
    kind = "crypto" if asset_kind == "crypto" else "us"
    requested = {
        s.strip().upper(): normalize_symbol(s, asset_kind)
        for s in symbols
        if s and s.strip()
    }
    result: dict[str, dict | None] = {s: None for s in requested}
    if asset_kind not in ("stock", "etf", "crypto"):
        return result

    now = time.time()
    found: dict[str, dict | None] = {}
    missing: list[str] = []
    for name in dict.fromkeys(requested.values()):
        cached = _cache.get((kind, name))
        if cached and now - cached[0] < _CACHE_TTL:
            found[name] = cached[1]
        elif name:
            missing.append(name)

    for start in range(0, len(missing), MAX_SYMBOLS):
        batch = missing[start : start + MAX_SYMBOLS]
        async with aiohttp.ClientSession() as session:
            fetched = await (
                _fetch_crypto(session, batch)
                if kind == "crypto"
                else _fetch_us(session, batch)
            )
        if fetched is None:
            continue
        for name, value in fetched.items():
            _cache[(kind, name)] = (now, value)
            found[name] = value

    for symbol, name in requested.items():
        result[symbol] = found.get(name)
    return result


async def get_symbol_indicators(symbol: str, asset_kind: str = "stock") -> dict | None:
    """:func:`get_indicators` for one symbol."""
    return (await get_indicators([symbol], asset_kind)).get(symbol.strip().upper())


if __name__ == "__main__":
    import json

    async def main() -> None:
        print(json.dumps(await get_indicators(["AAPL", "EWZ", "BRK-B"]), indent=2))
        print(json.dumps(await get_indicators(["BTC"], "crypto"), indent=2))

    asyncio.run(main())
