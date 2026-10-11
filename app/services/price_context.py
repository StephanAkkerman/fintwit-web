"""Longer-horizon price context for one symbol: 52-week/ATH stats plus trend.

Built for the market check, which otherwise only sees today's move. Combines
:func:`get_symbol_stats` (ATH/ATL, 52-week range and highlight flags) with a
one-year daily series summarised into returns and moving averages.
"""

import asyncio
from datetime import date, timedelta

from .price_history_service import get_price_series, get_symbol_stats

#: Lookback windows reported as returns, in calendar days.
RETURN_WINDOWS: dict[str, int] = {"1m": 30, "3m": 91, "6m": 182, "1y": 365}
SMA_WINDOWS = (50, 200)


def _close_on_or_before(points: list[dict], day: date) -> float | None:
    cutoff = day.isoformat()
    candidates = [p for p in points if p["t"][:10] <= cutoff]
    return candidates[-1]["close"] if candidates else None


def _pct(now: float, then: float | None) -> float | None:
    if not then:
        return None
    return round((now / then - 1) * 100, 2)


def summarize_trend(points: list[dict]) -> dict | None:
    """Returns over 1/3/6/12 months and distance from the 50/200-day averages.

    :param points: Chronological daily ``{t, close}`` points.
    :return: Trend dict, or ``None`` without data.
    """
    if not points:
        return None

    last = points[-1]
    latest = last["close"]
    as_of = date.fromisoformat(last["t"][:10])
    first_day = points[0]["t"][:10]

    returns: dict[str, float | None] = {}
    for label, days in RETURN_WINDOWS.items():
        start = as_of - timedelta(days=days)
        # Don't report a 1y return off a series that starts 3 months ago.
        if start.isoformat() < first_day:
            returns[label] = None
            continue
        returns[label] = _pct(latest, _close_on_or_before(points, start))

    closes = [p["close"] for p in points]
    averages: dict[str, dict] = {}
    for window in SMA_WINDOWS:
        if len(closes) < window:
            continue
        sma = sum(closes[-window:]) / window
        averages[f"sma_{window}"] = {
            "value": round(sma, 4),
            "price_vs_percent": _pct(latest, sma),
        }

    trend = None
    if "sma_50" in averages and "sma_200" in averages:
        fast = averages["sma_50"]["value"]
        slow = averages["sma_200"]["value"]
        if latest > fast > slow:
            trend = "uptrend"
        elif latest < fast < slow:
            trend = "downtrend"
        else:
            trend = "mixed"

    return {
        "as_of": last["t"][:10],
        "last_close": latest,
        "returns_percent": returns,
        **averages,
        "trend": trend,
    }


async def get_price_context(symbol: str, price: float | None = None) -> dict | None:
    """52-week/ATH statistics and the one-year trend for a symbol.

    :param symbol: Ticker symbol.
    :param price: Live price to measure the stats against; defaults to the
        latest close.
    :return: ``{"symbol", "stats", "trend"}``, or ``None`` with no history.
    """
    normalized = (symbol or "").strip().upper()
    if not normalized:
        return None

    stats, series = await asyncio.gather(
        get_symbol_stats(normalized, price), get_price_series(normalized, "1Y")
    )
    trend = summarize_trend(series)
    if stats is None and trend is None:
        return None
    return {"symbol": normalized, "stats": stats, "trend": trend}
