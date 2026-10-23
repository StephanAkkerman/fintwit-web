"""Weinstein trend stage and relative strength against the market and sector.

Stan Weinstein's stage analysis reads a weekly chart against its 30-week
moving average:

1. **Basing**: the average flattens out after a decline and price chops
   around it.
2. **Advancing**: price holds above a rising average (the only stage to buy).
3. **Topping**: the average flattens out after an advance.
4. **Declining**: price holds below a falling average (the stage to avoid).

Relative strength is his Mansfield variant: the price ratio against a
benchmark, compared with that ratio's own 52-week average, so ``0`` means
"keeping pace" and a positive number "outperforming lately". It is measured
against the market (SPY) and against the symbol's sector ETF, and the sector
ETF itself is staged and measured against the market, which together say
whether a stock is a leader in a leading group.

Everything is computed from Yahoo's weekly bars, fetched and cached by
`price_history_service`; this module does no fetching of its own.
"""

import asyncio
from datetime import date
from typing import Optional

from .fundamentals_service import get_valuation
from .price_history_service import get_price_series
from .sector_rotation_service import BENCHMARK, SECTOR_ETFS

MA_WEEKS = 30
RS_WEEKS = 52
#: The 30-week average's slope is its change over this many weeks.
SLOPE_WEEKS = 5
#: A 5-week change in the average below this (percent) counts as flat.
FLAT_SLOPE_PCT = 1.0
#: Price this close (percent) to the average, on the wrong side of it, is a
#: test of the average rather than a change of stage.
MA_TOLERANCE_PCT = 3.0
#: How far back to look for the trend a flat average came out of.
PRIOR_TREND_WEEKS = 15
#: Cap on how far back ``weeks_in_stage`` counts.
MAX_STAGE_LOOKBACK = 104

STAGE_NAMES = {1: "basing", 2: "advancing", 3: "topping", 4: "declining"}

#: Yahoo's sector names (as in yfinance ``info["sector"]``) -> SPDR sector ETF.
#: The GICS names `sector_rotation_service` uses are accepted too.
_YAHOO_SECTORS = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Healthcare": "XLV",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
}


def sector_etf(sector: str | None) -> str | None:
    """The SPDR Select Sector ETF for a Yahoo or GICS sector name."""
    if not sector:
        return None
    return _YAHOO_SECTORS.get(sector) or SECTOR_ETFS.get(sector)


def _sma(values: list[float], window: int, end: int) -> Optional[float]:
    """Average of ``values[end - window + 1 : end + 1]``, or None if short."""
    if end + 1 < window:
        return None
    chunk = values[end + 1 - window : end + 1]
    return sum(chunk) / window


def _pct(now: float, then: Optional[float]) -> Optional[float]:
    if not then:
        return None
    return round((now / then - 1) * 100, 2)


def _stage_at(closes: list[float], end: int) -> Optional[int]:
    """The Weinstein stage of the week at index ``end``."""
    ma = _sma(closes, MA_WEEKS, end)
    ma_before = _sma(closes, MA_WEEKS, end - SLOPE_WEEKS)
    if ma is None or ma_before is None:
        return None
    slope = (ma / ma_before - 1) * 100
    distance = (closes[end] / ma - 1) * 100
    above = distance >= 0

    if slope > FLAT_SLOPE_PCT:
        return 2 if distance > -MA_TOLERANCE_PCT else 3
    if slope < -FLAT_SLOPE_PCT:
        return 4 if distance < MA_TOLERANCE_PCT else 1

    # A flat average: a base if it came out of a decline, a top if out of an
    # advance. Without enough history to tell, price above it reads as a top.
    ma_prior = _sma(closes, MA_WEEKS, end - PRIOR_TREND_WEEKS)
    if ma_prior is None:
        return 3 if above else 1
    return 1 if ma_prior > ma else 3


def stage_analysis(points: list[dict]) -> Optional[dict]:
    """Weinstein stage of a weekly series, with the numbers behind it.

    :param points: Chronological weekly ``{t, close}`` points.
    :return: ``None`` when there are fewer than 35 weeks to read.
    """
    closes = [p["close"] for p in points if p.get("close") is not None]
    last = len(closes) - 1
    stage = _stage_at(closes, last)
    if stage is None:
        return None

    weeks = 1
    while weeks < MAX_STAGE_LOOKBACK and _stage_at(closes, last - weeks) == stage:
        weeks += 1

    ma = _sma(closes, MA_WEEKS, last)
    ma_before = _sma(closes, MA_WEEKS, last - SLOPE_WEEKS)
    previous = None
    for offset in range(weeks, min(weeks + MAX_STAGE_LOOKBACK, last)):
        previous = _stage_at(closes, last - offset)
        if previous is not None:
            break

    return {
        "stage": stage,
        "name": STAGE_NAMES[stage],
        "weeks_in_stage": weeks,
        "previous_stage": previous,
        "ma30w": round(ma, 4),
        "price_vs_ma30w_percent": _pct(closes[last], ma),
        "ma30w_slope_5w_percent": _pct(ma, ma_before),
    }


def _week_key(point: dict) -> tuple[int, int]:
    """ISO (year, week): Yahoo dates the running week's bar differently from
    the finished ones, so weeks are matched by number rather than by date."""
    iso = date.fromisoformat(point["t"][:10]).isocalendar()
    return iso[0], iso[1]


def relative_strength(points: list[dict], benchmark: list[dict]) -> Optional[dict]:
    """Mansfield relative strength and 13/26-week performance against a
    benchmark, both weekly series.

    :return: ``mansfield`` (percent above the ratio's 52-week average),
        whether it is rising over 4 weeks, and the return difference in
        percentage points over 13 and 26 weeks; ``None`` without overlap.
    """
    bench = {_week_key(p): p["close"] for p in benchmark if p.get("close")}
    pairs = [
        (p["close"], bench[_week_key(p)])
        for p in points
        if p.get("close") and _week_key(p) in bench
    ]
    if len(pairs) < 14:
        return None

    ratio = [own / ref for own, ref in pairs]
    last = len(ratio) - 1

    def mansfield(end: int) -> Optional[float]:
        avg = _sma(ratio, RS_WEEKS, end)
        return None if avg is None else round((ratio[end] / avg - 1) * 100, 2)

    def outperformance(weeks: int) -> Optional[float]:
        if last < weeks:
            return None
        own_now, ref_now = pairs[last]
        own_then, ref_then = pairs[last - weeks]
        return round(
            ((own_now / own_then) - (ref_now / ref_then)) * 100,
            2,
        )

    now = mansfield(last)
    before = mansfield(last - 4) if last >= 4 else None
    return {
        "mansfield": now,
        "mansfield_rising_4w": (
            None if now is None or before is None else now > before
        ),
        "outperformance_13w_pp": outperformance(13),
        "outperformance_26w_pp": outperformance(26),
    }


async def get_trend_stage(symbol: str) -> Optional[dict]:
    """Weinstein stage plus relative strength vs the market and the sector.

    :param symbol: Ticker symbol.
    :return: ``{symbol, as_of, stage, vs_market, sector}``; ``sector`` is
        ``None`` for funds, crypto and anything Yahoo has no sector for.
        ``None`` when the symbol has under 35 weeks of history.
    """
    normalized = (symbol or "").strip().upper()
    if not normalized:
        return None

    series, market, valuation = await asyncio.gather(
        get_price_series(normalized, "5Y"),
        get_price_series(BENCHMARK, "5Y"),
        get_valuation(normalized),
    )
    stage = stage_analysis(series)
    if stage is None:
        return None

    sector_name = (valuation or {}).get("sector")
    etf = sector_etf(sector_name)
    sector = None
    if etf and etf != normalized:
        etf_series = await get_price_series(etf, "5Y")
        sector = {
            "name": sector_name,
            "etf": etf,
            "stage": stage_analysis(etf_series),
            "vs_market": relative_strength(etf_series, market),
            "stock_vs_sector": relative_strength(series, etf_series),
        }

    return {
        "symbol": normalized,
        "as_of": series[-1]["t"][:10],
        "stage": stage,
        "vs_market": relative_strength(series, market) if market else None,
        "benchmark": BENCHMARK,
        "sector": sector,
    }
