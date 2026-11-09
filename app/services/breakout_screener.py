"""Stage-2 breakout screener: stocks that just moved into a weekly uptrend.

Stan Weinstein's buy point is the week a stock leaves a base (stage 1) and
starts holding above a rising 30-week moving average (stage 2). He wanted
three things to line up on that breakout:

* **The stage change itself**, and early: a stock that entered stage 2
  months ago is extended, and the risk to its 30-week average is too wide.
* **Relative strength**: the stock is beating the market (Mansfield RS above
  zero) and the lead is growing, so the move is the stock's own and not just
  the tide.
* **Volume**: the breakout week trades well above the volume of the weeks in
  the base. He asked for twice the average; this screen asks for 1.5x and
  reports the ratio so a reader can hold out for more.

:func:`evaluate_breakout` checks all of it on one weekly series and is pure:
given ``end`` it only reads bars up to that week, so a backtest can walk a
history week by week without look-ahead (:func:`breakout_weeks` does exactly
that). The live screen (:func:`run_screen`) first narrows the US market to a
few hundred plausible names with one TradingView scanner request (price above
a rising 30-week average, enough size and liquidity), then evaluates each on
Yahoo's weekly bars from `price_history_service`, the same bars
`trend_stage` reads, so the screen, the per-ticker stage and a backtest all
agree on what a breakout is.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from .price_history_service import get_price_series
from .sector_rotation_service import BENCHMARK
from .trend_stage import (
    MA_WEEKS,
    MAX_STAGE_LOOKBACK,
    SLOPE_WEEKS,
    _stage_at,
    relative_strength,
    stage_analysis,
)

logger = logging.getLogger(__name__)

#: A breakout at most this many weeks old (counted from the week price
#: cleared the 30-week average) still counts as fresh.
FRESH_WEEKS = 8
#: The 30-week average needs a few weeks to turn up after price clears it, so
#: stage 2 (a *rising* average) starts later than the breakout itself. A cross
#: up to this many weeks before stage 2 began is taken as its start.
MAX_CROSS_LEAD_WEEKS = 6
#: The breakout's volume against the average of the base weeks before it.
MIN_VOLUME_RATIO = 1.5
#: Weinstein's own bar for a convincing breakout; reported as ``strong``.
STRONG_VOLUME_RATIO = 2.0
#: How many weeks before the breakout make up the "base" volume average.
VOLUME_BASE_WEEKS = 10
#: Mansfield RS (percent above its 52-week average) must be above this.
MIN_MANSFIELD = 0.0
#: Price further than this (percent) above the 30-week average is extended.
MAX_EXTENSION_PCT = 25.0
#: Stages a breakout may come out of: a base (1) or a pause after an earlier
#: advance that the average had flattened out on (3). Straight out of a
#: decline (4) is a bounce until it has based.
ENTRY_FROM = (1, 3)
#: ...and that base must have lasted this long: a week or two of a flat
#: average inside a long advance is a pause, not a base to break out of.
MIN_BASE_WEEKS = 6
#: The thresholds above, as the API reports them next to a screen.
CRITERIA = {
    "fresh_weeks": FRESH_WEEKS,
    "ma_weeks": MA_WEEKS,
    "min_volume_ratio": MIN_VOLUME_RATIO,
    "strong_volume_ratio": STRONG_VOLUME_RATIO,
    "min_mansfield": MIN_MANSFIELD,
    "max_extension_pct": MAX_EXTENSION_PCT,
    "min_base_weeks": MIN_BASE_WEEKS,
}
#: Enough weekly bars for the 30-week average, its slope, and a stage before.
MIN_WEEKS = MA_WEEKS + SLOPE_WEEKS + 2

# --- Live screen -------------------------------------------------------------

_SCANNER_URL = "https://scanner.tradingview.com/america/scan"
_SCANNER_TIMEOUT = aiohttp.ClientTimeout(total=20)
_SCANNER_COLUMNS = [
    "name",
    "description",
    "close",
    "sector",
    "industry",
    "market_cap_basic",
    "Perf.3M",
    "relative_volume_10d_calc|1W",
    "volume[1]|1W",
    "average_volume_10d_calc[1]|1W",
]
#: Names the scanner hands to Yahoo, split between the strongest 3-month
#: performers and the busiest weeks (a fresh breakout from a long base has
#: often not gone far yet, but its volume gives it away).
DEFAULT_CANDIDATES = 240
_MAX_SCANNER_ROWS = 3000
#: Yahoo fetches run through `price_history_service`'s own limiter; this keeps
#: the screen from queueing hundreds of coroutines at once on top of it.
_EVAL_CONCURRENCY = 6
#: Near misses kept per run: fresh stage-2 entries that fail one check.
MAX_WATCH = 40


def _min_market_cap() -> float:
    return float(os.getenv("BREAKOUT_MIN_MARKET_CAP", "1000000000"))


def _candidate_limit() -> int:
    try:
        return max(20, int(os.getenv("BREAKOUT_CANDIDATES", DEFAULT_CANDIDATES)))
    except ValueError:
        return DEFAULT_CANDIDATES


def _mean(values: list[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _breakout_start(closes: list[float], last: int, stage_start: int) -> int:
    """The week the current advance began: when price closed above its
    30-week average and stayed there, if that was shortly before stage 2
    began; otherwise the start of stage 2 itself."""
    cross = last + 1
    while cross - 1 >= MA_WEEKS - 1:
        index = cross - 1
        ma = sum(closes[index + 1 - MA_WEEKS : index + 1]) / MA_WEEKS
        if closes[index] <= ma:
            break
        cross = index
    if cross <= stage_start and stage_start - cross <= MAX_CROSS_LEAD_WEEKS:
        return cross
    return stage_start


def _base_weeks(closes: list[float], stage_start: int) -> int:
    """How many weeks before ``stage_start`` were a base (stage 1 or 3)."""
    weeks = 0
    index = stage_start - 1
    while weeks < MAX_STAGE_LOOKBACK and _stage_at(closes, index) in ENTRY_FROM:
        weeks += 1
        index -= 1
    return weeks


def _volume_ratio(points: list[dict], start: int, last: int) -> Optional[dict]:
    """Breakout volume against the base's: the busiest week since ``start``
    (price often clears the average on a wiggle inside the base and only
    surges out of it a week or two later) over the average of the
    ``VOLUME_BASE_WEEKS`` weeks before ``start``."""
    base = [
        p.get("volume")
        for p in points[max(0, start - VOLUME_BASE_WEEKS) : start]
        if p.get("volume")
    ]
    window = [
        p.get("volume")
        for p in points[start : min(last, start + FRESH_WEEKS - 1) + 1]
        if p.get("volume")
    ]
    base_avg = _mean(base)
    if not base_avg or len(base) < VOLUME_BASE_WEEKS // 2 or not window:
        return None
    peak = max(window)
    return {
        "ratio": round(peak / base_avg, 2),
        "breakout_week_volume": peak,
        "base_avg_volume": round(base_avg),
    }


def evaluate_breakout(
    points: list[dict], benchmark: list[dict], end: Optional[int] = None
) -> Optional[dict]:
    """Whether a weekly series is in a fresh stage-2 breakout as of week ``end``.

    :param points: Chronological weekly ``{t, close, volume}`` bars.
    :param benchmark: The market's weekly bars (SPY) for relative strength;
        bars after ``points[end]`` are never matched, so it needn't be cut.
    :param end: Index into ``points`` to evaluate at; the last bar if None.
    :return: ``None`` when there is too little history to stage. Otherwise
        the stage numbers, relative strength, volume and extension, a
        ``checks`` dict with each criterion's verdict, ``signal`` (all of them
        pass) and ``failed`` (the checks that did not).
    """
    usable = [p for p in points if p.get("close") is not None]
    if end is not None:
        # ``end`` indexes ``points``; translate it to the filtered list.
        cutoff = points[end]["t"] if 0 <= end < len(points) else None
        if cutoff is None:
            return None
        usable = [p for p in usable if p["t"] <= cutoff]
    if len(usable) < MIN_WEEKS:
        return None

    stage = stage_analysis(usable)
    if stage is None:
        return None

    last = len(usable) - 1
    weeks = stage["weeks_in_stage"]
    start = last - weeks + 1
    base_weeks = None
    if stage["stage"] == 2:
        closes = [p["close"] for p in usable]
        base_weeks = _base_weeks(closes, start)
        start = _breakout_start(closes, last, start)
    since = last - start + 1
    rs = relative_strength(usable, benchmark) if benchmark else None
    volume = _volume_ratio(usable, start, last) if stage["stage"] == 2 else None
    extension = stage["price_vs_ma30w_percent"]
    mansfield = (rs or {}).get("mansfield")

    checks = {
        "stage_2": stage["stage"] == 2,
        "fresh": stage["stage"] == 2 and since <= FRESH_WEEKS,
        "from_base": stage["previous_stage"] in ENTRY_FROM
        and (base_weeks or 0) >= MIN_BASE_WEEKS,
        "relative_strength": mansfield is not None and mansfield > MIN_MANSFIELD,
        "rs_rising": bool((rs or {}).get("mansfield_rising_4w")),
        "volume": volume is not None and volume["ratio"] >= MIN_VOLUME_RATIO,
        "not_extended": extension is not None and extension <= MAX_EXTENSION_PCT,
    }
    failed = [name for name, ok in checks.items() if not ok]

    return {
        "as_of": usable[last]["t"][:10],
        "close": usable[last]["close"],
        "stage": stage["stage"],
        "stage_name": stage["name"],
        "weeks_in_stage": weeks,
        "weeks_since_breakout": since if stage["stage"] == 2 else None,
        "entered_from": stage["previous_stage"],
        "base_weeks": base_weeks,
        "breakout_week": usable[start]["t"][:10] if stage["stage"] == 2 else None,
        "breakout_close": usable[start]["close"] if stage["stage"] == 2 else None,
        "ma30w": stage["ma30w"],
        "ma30w_slope_5w_percent": stage["ma30w_slope_5w_percent"],
        "price_vs_ma30w_percent": extension,
        "mansfield_rs": mansfield,
        "rs_rising_4w": (rs or {}).get("mansfield_rising_4w"),
        "outperformance_13w_pp": (rs or {}).get("outperformance_13w_pp"),
        "volume_ratio": volume["ratio"] if volume else None,
        "strong_volume": bool(volume and volume["ratio"] >= STRONG_VOLUME_RATIO),
        "checks": checks,
        "failed": failed,
        "signal": not failed,
        "score": _score(since, mansfield, volume, extension) if not failed else None,
    }


def _score(
    weeks: int,
    mansfield: Optional[float],
    volume: Optional[dict],
    extension: Optional[float],
) -> float:
    """Rank breakouts, best first: strong RS and volume, early, not stretched.

    A rough 0-100 blend: relative strength (up to 40 points at +40% Mansfield),
    volume (up to 30 at 4x the base), freshness (20 in the first week, fading
    to 0 at ``FRESH_WEEKS``) and closeness to the average (10 at the line,
    0 at ``MAX_EXTENSION_PCT``).
    """
    rs_part = min(max(mansfield or 0.0, 0.0), 40.0)
    vol_part = min(max(((volume or {}).get("ratio") or 0.0) - 1.0, 0.0), 3.0) * 10
    fresh_part = 20 * (FRESH_WEEKS - weeks + 1) / FRESH_WEEKS
    ext = min(max(extension or 0.0, 0.0), MAX_EXTENSION_PCT)
    ext_part = 10 * (1 - ext / MAX_EXTENSION_PCT)
    return round(rs_part + vol_part + fresh_part + ext_part, 1)


def breakout_weeks(points: list[dict], benchmark: list[dict]) -> list[dict]:
    """Every week a series *newly* flagged a breakout, for backtests.

    Walks the history week by week with :func:`evaluate_breakout`, so each
    entry only knows what was known that week. A breakout keeps passing for
    several weeks; only the first week of each run is returned, which is the
    week a live screen would have flagged it.

    :return: Chronological ``{t, close, score, volume_ratio, mansfield_rs,
        weeks_since_breakout}`` dicts; ``t`` is the week's bar date.
    """
    signals: list[dict] = []
    previous = False
    for index in range(MIN_WEEKS - 1, len(points)):
        if points[index].get("close") is None:
            continue
        result = evaluate_breakout(points, benchmark, end=index)
        firing = bool(result and result["signal"])
        if firing and not previous:
            signals.append(
                {
                    "t": result["as_of"],
                    "close": result["close"],
                    "score": result["score"],
                    "volume_ratio": result["volume_ratio"],
                    "mansfield_rs": result["mansfield_rs"],
                    "weeks_since_breakout": result["weeks_since_breakout"],
                }
            )
        previous = firing
    return signals


# --- Live screen -------------------------------------------------------------


def _yahoo_symbol(name: str) -> str:
    """TradingView writes share classes with a dot (BRK.B), Yahoo a dash."""
    return name.replace(".", "-").upper()


def parse_candidate(row: dict) -> Optional[dict]:
    """Map one scanner row (``{"s": "NASDAQ:AAPL", "d": [...]}``) to a dict."""
    values = row.get("d") if isinstance(row, dict) else None
    if not isinstance(values, list) or len(values) < len(_SCANNER_COLUMNS):
        return None
    data = dict(zip(_SCANNER_COLUMNS, values))
    name = data.get("name")
    if not isinstance(name, str) or not name:
        return None
    exchange = str(row.get("s") or "").split(":")[0] or None
    # The running week's relative volume is tiny early in the week, so the
    # last finished week counts too: a breakout often landed then.
    last_week = None
    volume, average = (
        data.get("volume[1]|1W"),
        data.get("average_volume_10d_calc[1]|1W"),
    )
    if (
        isinstance(volume, (int, float))
        and isinstance(average, (int, float))
        and average
    ):
        last_week = volume / average
    relative = [
        v
        for v in (data.get("relative_volume_10d_calc|1W"), last_week)
        if isinstance(v, (int, float))
    ]
    return {
        "symbol": _yahoo_symbol(name),
        "name": data.get("description") or name,
        "exchange": exchange,
        "sector": data.get("sector"),
        "industry": data.get("industry"),
        "market_cap": data.get("market_cap_basic"),
        "perf_3m": data.get("Perf.3M"),
        "relative_volume_1w": round(max(relative), 2) if relative else None,
    }


def pick_candidates(rows: list[dict], limit: int) -> list[dict]:
    """Half the slots to the best 3-month performers, the rest to the
    heaviest weekly relative volume, without duplicates."""

    def by(field: str) -> list[dict]:
        return sorted(
            (r for r in rows if r.get(field) is not None),
            key=lambda r: r[field],
            reverse=True,
        )

    picked: dict[str, dict] = {}
    for row in by("perf_3m")[: limit // 2]:
        picked[row["symbol"]] = row
    for row in by("relative_volume_1w"):
        if len(picked) >= limit:
            break
        picked.setdefault(row["symbol"], row)
    return list(picked.values())


async def fetch_candidates(limit: Optional[int] = None) -> Optional[list[dict]]:
    """US stocks above a rising 30-week average, narrowed to ``limit`` names.

    :return: Candidate dicts (see :func:`parse_candidate`), or ``None`` when
        the scanner could not be reached.
    """
    payload = {
        "columns": _SCANNER_COLUMNS,
        "filter": [
            {"left": "type", "operation": "equal", "right": "stock"},
            {
                "left": "subtype",
                "operation": "in_range",
                "right": ["common", "foreign-issuer"],
            },
            {
                "left": "exchange",
                "operation": "in_range",
                "right": ["NYSE", "NASDAQ", "AMEX"],
            },
            {
                "left": "market_cap_basic",
                "operation": "egreater",
                "right": _min_market_cap(),
            },
            {"left": "average_volume_30d_calc", "operation": "greater", "right": 2e5},
            {"left": "close", "operation": "greater", "right": 5},
            # Weekly close above a rising 30-week average: stage 2 as the
            # scanner sees it. Yahoo's bars then decide whether it is fresh.
            {"left": "close|1W", "operation": "greater", "right": "SMA30|1W"},
            {"left": "SMA30|1W", "operation": "greater", "right": "SMA30[1]|1W"},
        ],
        "sort": {"sortBy": "Perf.3M", "sortOrder": "desc"},
        "range": [0, _MAX_SCANNER_ROWS],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _SCANNER_URL, json=payload, timeout=_SCANNER_TIMEOUT
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        "[breakouts] scanner returned status=%s", resp.status
                    )
                    return None
                body = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        logger.warning("[breakouts] scanner request failed: %r", exc)
        return None

    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list):
        return None
    rows = [c for c in (parse_candidate(r) for r in data) if c is not None]
    return pick_candidates(rows, limit or _candidate_limit())


async def run_screen(limit: Optional[int] = None) -> Optional[dict]:
    """Screen the US market for fresh stage-2 breakouts.

    :param limit: Names to evaluate on Yahoo's weekly bars after the scanner
        pass; ``BREAKOUT_CANDIDATES`` (default 240) when None.
    :return: ``{ran_at, as_of, universe, evaluated, breakouts, watch}``, best
        first; ``watch`` holds fresh stage-2 entries that miss one check.
        ``None`` when the scanner or the SPY history could not be fetched.
    """
    candidates = await fetch_candidates(limit)
    if candidates is None:
        return None
    market = await get_price_series(BENCHMARK, "5Y")
    if not market:
        logger.warning("[breakouts] no %s history, skipping the screen", BENCHMARK)
        return None

    limiter = asyncio.Semaphore(_EVAL_CONCURRENCY)

    async def evaluate(candidate: dict) -> Optional[dict]:
        async with limiter:
            series = await get_price_series(candidate["symbol"], "5Y")
        if not series:
            return None
        result = evaluate_breakout(series, market)
        if result is None:
            return None
        return {**candidate, **result}

    results = [
        r
        for r in await asyncio.gather(*(evaluate(c) for c in candidates))
        if r is not None
    ]
    breakouts = sorted(
        (r for r in results if r["signal"]), key=lambda r: r["score"], reverse=True
    )
    # Near misses: a fresh stage-2 entry out of a base that fails exactly one
    # other check, usually volume or RS that hasn't caught up yet.
    watch = sorted(
        (
            r
            for r in results
            if not r["signal"]
            and r["checks"]["fresh"]
            and r["checks"]["from_base"]
            and len(r["failed"]) == 1
        ),
        key=lambda r: ((r["mansfield_rs"] or 0), (r["volume_ratio"] or 0)),
        reverse=True,
    )[:MAX_WATCH]
    as_of = max((r["as_of"] for r in results), default=None)
    return {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "as_of": as_of,
        "universe": len(candidates),
        "evaluated": len(results),
        "benchmark": BENCHMARK,
        "breakouts": breakouts,
        "watch": watch,
    }
