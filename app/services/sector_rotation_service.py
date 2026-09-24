"""Relative Rotation Graph (RRG) data for sector rotation vs. a benchmark.

An RRG plots each sector's *JdK RS-Ratio* (is it outperforming the benchmark,
and is that trend strengthening or fading?) against its *JdK RS-Momentum*
(the rate of change of that trend), so a sector's trail across the four
quadrants shows whether it is leading, weakening, lagging, or improving
relative to the market. See e.g. https://github.com/An0n1mity/RRGPy for a
reference implementation of the same JdK formulas this module follows,
adapted here to use a rolling (rather than fixed-anchor) rate of change so it
stays well-behaved over long trails.

Both the relative-strength line and its rate of change are EMA-smoothed before
normalization, as the JdK method prescribes. Without that, one day's noise
decides each step's direction and a trail is a random zig-zag instead of the
rotation the chart is meant to show.

`ticker-price-data` only exposes live quotes, so history comes from
`price_history_service`, which already fetches and caches it -- this module
does no fetching of its own.
"""

import asyncio
import logging
from statistics import fmean, pstdev
from typing import Callable, Optional

from .price_history_service import get_price_series

logger = logging.getLogger(__name__)

BENCHMARK = "SPY"

#: GICS sector -> SPDR Select Sector ETF. Sector names match `sectorStyle.ts`
#: so the RRG shares icons/colors with `SectorOverviewWidget`.
SECTOR_ETFS: dict[str, str] = {
    "Technology": "XLK",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
}

TIMEFRAMES = ("daily", "weekly")
DEFAULT_TIMEFRAME = "daily"

# Yahoo range/interval fetched per timeframe -- "weekly" pulls Yahoo's own
# weekly bars (5 years of them) rather than resampling daily closes.
_FETCH_RANGE_BY_TIMEFRAME = {"daily": "1Y", "weekly": "5Y"}

RS_WINDOW = 14
#: EMA span applied to relative strength and to its rate of change. 5 bars
#: halves the per-step jitter of the trail without lagging turns by more than a
#: couple of bars.
RS_SMOOTHING = 5
DEFAULT_TAIL = 10
MIN_TAIL = 3
MAX_TAIL = 20


def normalize_timeframe(value: str | None) -> str:
    """Return a supported timeframe key, falling back to :data:`DEFAULT_TIMEFRAME`."""
    key = (value or "").strip().lower()
    return key if key in TIMEFRAMES else DEFAULT_TIMEFRAME


def clamp_tail(value: int | None) -> int:
    """Clamp a requested trail length to a sane, renderable range."""
    if value is None:
        return DEFAULT_TAIL
    return max(MIN_TAIL, min(MAX_TAIL, value))


def _closes_by_date(points: list[dict]) -> dict[str, float]:
    return {p["t"][:10]: p["close"] for p in points if p.get("close") is not None}


def _rolling(
    values: list[Optional[float]], window: int, fn: Callable[[list[float]], float]
) -> list[Optional[float]]:
    """Apply ``fn`` over a trailing window, ``None`` until the window fills or
    hits a ``None`` value.
    """
    out: list[Optional[float]] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
            continue
        chunk = values[i + 1 - window : i + 1]
        out.append(None if any(v is None for v in chunk) else fn(chunk))
    return out


def _ema(values: list[Optional[float]], span: int) -> list[Optional[float]]:
    """Exponential moving average with ``alpha = 2 / (span + 1)``.

    ``None`` passes through and restarts the average, so a gap never blends
    values from either side of it. ``span <= 1`` returns the input unchanged.
    """
    if span <= 1:
        return list(values)
    alpha = 2.0 / (span + 1)
    out: list[Optional[float]] = []
    prev: Optional[float] = None
    for v in values:
        if v is None:
            prev = None
        else:
            prev = v if prev is None else alpha * v + (1 - alpha) * prev
        out.append(prev)
    return out


def compute_rs_ratio_momentum(
    sector_closes: list[float],
    benchmark_closes: list[float],
    window: int = RS_WINDOW,
    smoothing: int = RS_SMOOTHING,
) -> tuple[list[Optional[float]], list[Optional[float]]]:
    """Return the JdK RS-Ratio and RS-Momentum series for aligned closes.

    :param sector_closes: Sector closes, chronological, aligned 1:1 by date
        with ``benchmark_closes``.
    :param benchmark_closes: Benchmark closes.
    :param window: Rolling window used for both normalization stages.
    :param smoothing: EMA span applied to relative strength and to its rate of
        change before each is normalized; ``1`` disables smoothing.
    :return: ``(rs_ratio, rs_momentum)``, each the same length as the inputs;
        ``None`` wherever there isn't yet enough history to normalize.
    """
    n = len(sector_closes)
    rs = _ema(
        [100.0 * s / b for s, b in zip(sector_closes, benchmark_closes)], smoothing
    )

    rs_mean = _rolling(rs, window, fmean)
    rs_std = _rolling(rs, window, pstdev)
    rs_ratio: list[Optional[float]] = [
        100.0 + (rs[i] - rs_mean[i]) / rs_std[i]
        if rs_mean[i] is not None and rs_std[i]
        else None
        for i in range(n)
    ]

    # Rate of change of the RS-Ratio itself: is the outperformance trend
    # accelerating or fading? Normalized the same way as RS-Ratio.
    roc: list[Optional[float]] = [None]
    for i in range(1, n):
        prev, curr = rs_ratio[i - 1], rs_ratio[i]
        roc.append(100.0 * (curr / prev - 1) if prev and curr is not None else None)
    roc = _ema(roc, smoothing)

    roc_mean = _rolling(roc, window, fmean)
    roc_std = _rolling(roc, window, pstdev)
    rs_momentum: list[Optional[float]] = [
        100.0 + (roc[i] - roc_mean[i]) / roc_std[i]
        if roc[i] is not None and roc_mean[i] is not None and roc_std[i]
        else None
        for i in range(n)
    ]

    return rs_ratio, rs_momentum


def classify_quadrant(rs_ratio: float, rs_momentum: float) -> str:
    """Name the RRG quadrant a ``(rs_ratio, rs_momentum)`` point falls in."""
    if rs_ratio >= 100:
        return "leading" if rs_momentum >= 100 else "weakening"
    return "improving" if rs_momentum >= 100 else "lagging"


async def get_sector_rotation(
    timeframe: str = DEFAULT_TIMEFRAME,
    tail: int = DEFAULT_TAIL,
    window: int = RS_WINDOW,
) -> dict:
    """Build RRG trails for every sector ETF against :data:`BENCHMARK`.

    :param timeframe: ``"daily"`` or ``"weekly"`` bars.
    :param tail: How many trailing points each sector's trail should carry.
    :param window: Rolling window for the RS-Ratio/RS-Momentum normalization.
    :return: ``{"timeframe", "benchmark", "window", "sectors": [...]}``, each
        sector carrying its ETF, current quadrant, and a chronological trail
        of ``{date, rs_ratio, rs_momentum}`` points. Sectors without enough
        history to compute even one point are omitted.
    """
    timeframe = normalize_timeframe(timeframe)
    tail = clamp_tail(tail)
    fetch_range = _FETCH_RANGE_BY_TIMEFRAME[timeframe]

    symbols = [BENCHMARK, *SECTOR_ETFS.values()]
    series_list = await asyncio.gather(
        *(get_price_series(symbol, fetch_range) for symbol in symbols),
        return_exceptions=True,
    )

    series_by_symbol: dict[str, list[dict]] = {}
    for symbol, series in zip(symbols, series_list):
        if isinstance(series, Exception):
            logger.debug("[sector-rotation] %s fetch failed: %r", symbol, series)
            series_by_symbol[symbol] = []
        else:
            series_by_symbol[symbol] = series

    benchmark_closes = _closes_by_date(series_by_symbol.get(BENCHMARK, []))
    empty_result = {
        "timeframe": timeframe,
        "benchmark": BENCHMARK,
        "window": window,
        "sectors": [],
    }
    if not benchmark_closes:
        return empty_result

    sectors: list[dict] = []
    for sector_name, etf in SECTOR_ETFS.items():
        sector_closes = _closes_by_date(series_by_symbol.get(etf, []))
        common_dates = sorted(d for d in sector_closes if d in benchmark_closes)
        if not common_dates:
            continue

        rs_ratio, rs_momentum = compute_rs_ratio_momentum(
            [sector_closes[d] for d in common_dates],
            [benchmark_closes[d] for d in common_dates],
            window,
        )

        trail = [
            {
                "date": date_str,
                "rs_ratio": round(ratio, 3),
                "rs_momentum": round(momentum, 3),
            }
            for date_str, ratio, momentum in zip(common_dates, rs_ratio, rs_momentum)
            if ratio is not None and momentum is not None
        ][-tail:]
        if not trail:
            continue

        latest = trail[-1]
        sectors.append(
            {
                "sector": sector_name,
                "etf": etf,
                "quadrant": classify_quadrant(
                    latest["rs_ratio"], latest["rs_momentum"]
                ),
                "trail": trail,
            }
        )

    return {**empty_result, "sectors": sectors}
