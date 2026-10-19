"""Market breadth: how many stocks take part in the index's move.

An index can rise on a handful of megacaps while most of its members fall, and
that kind of narrow rally tends to be fragile. Breadth measures the
participation behind the headline number: how many members advanced or
declined today, how many trade above their 20/50/200-day moving averages, and
how many set a new 52-week high or low.

Every figure is computed here from the constituents of each index, pulled in a
single TradingView Scanner request per index (the same public scanner
``market_movers_service`` uses). The scanner's ``symbolset`` filter lists an
index's members, so no constituent list has to be maintained by hand.

A "new high" is a member whose intraday high today reached its 52-week high
(the scanner's 52-week range includes today), and vice versa for lows.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

import aiohttp
import exchange_calendars as xcals
import pandas as pd

logger = logging.getLogger(__name__)

_SCANNER_URL = "https://scanner.tradingview.com/america/scan"
_CACHE_TTL = 300  # seconds
_TIMEOUT = aiohttp.ClientTimeout(total=15)

#: (key, label, scanner symbolset, benchmark ETF as EXCHANGE:SYMBOL)
UNIVERSES: list[tuple[str, str, str, str]] = [
    ("spx", "S&P 500", "SYML:SP;SPX", "AMEX:SPY"),
    ("ndx", "Nasdaq 100", "SYML:NASDAQ;NDX", "NASDAQ:QQQ"),
    ("rut", "Russell 2000", "SYML:TVC;RUT", "AMEX:IWM"),
]
UNIVERSE_KEYS = tuple(key for key, *_ in UNIVERSES)

_COLUMNS = [
    "name",
    "close",
    "change",
    "SMA20",
    "SMA50",
    "SMA200",
    "price_52_week_high",
    "price_52_week_low",
    "high",
    "low",
    "sector",
]
#: The Russell 2000 has ~2,000 members; leave headroom for index changes.
_MAX_MEMBERS = 2500

#: Share of members above their 200-day average, read as the market's state.
#: Checked top-down; the first threshold the value reaches wins.
_TREND_LEVELS: list[tuple[float, str, str]] = [
    (80.0, "overbought", "Overbought"),
    (60.0, "healthy", "Healthy"),
    (40.0, "mixed", "Mixed"),
    (20.0, "weak", "Weak"),
    (0.0, "washed_out", "Washed out"),
]
#: A benchmark move this size counts as a real up or down day.
_INDEX_MOVE_PCT = 0.25

_cache: tuple[float, dict] | None = None
_lock = asyncio.Lock()
_calendar: xcals.ExchangeCalendar | None = None


def _reset_cache_for_tests() -> None:
    global _cache
    _cache = None


def _num(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_member(row: dict) -> dict | None:
    """Map one scanner row (``{"s": ..., "d": [...]}``) to a member dict."""
    values = row.get("d") if isinstance(row, dict) else None
    if not isinstance(values, list) or len(values) < len(_COLUMNS):
        return None
    fields = dict(zip(_COLUMNS, values))
    close = _num(fields["close"])
    if close is None:
        return None
    return {
        "symbol": str(fields["name"] or row.get("s", "")),
        "close": close,
        "change": _num(fields["change"]),
        "sma20": _num(fields["SMA20"]),
        "sma50": _num(fields["SMA50"]),
        "sma200": _num(fields["SMA200"]),
        "high_52w": _num(fields["price_52_week_high"]),
        "low_52w": _num(fields["price_52_week_low"]),
        "high": _num(fields["high"]),
        "low": _num(fields["low"]),
        "sector": fields["sector"] or None,
    }


def _pct(count: int, total: int) -> float | None:
    return round(count / total * 100, 1) if total else None


def _above_share(members: list[dict], field: str) -> float | None:
    """Share of members closing above ``field``, among those that have it."""
    known = [m for m in members if m[field] is not None]
    return _pct(sum(1 for m in known if m["close"] > m[field]), len(known))


def _counts(members: list[dict]) -> dict:
    advancers = sum(1 for m in members if (m["change"] or 0) > 0)
    decliners = sum(1 for m in members if (m["change"] or 0) < 0)
    new_highs = sum(
        1
        for m in members
        if m["high"] is not None
        and m["high_52w"] is not None
        and m["high"] >= m["high_52w"]
    )
    new_lows = sum(
        1
        for m in members
        if m["low"] is not None
        and m["low_52w"] is not None
        and m["low"] <= m["low_52w"]
    )
    return {
        "members": len(members),
        "advancers": advancers,
        "decliners": decliners,
        "unchanged": len(members) - advancers - decliners,
        "advancers_pct": _pct(advancers, len(members)),
        "new_highs": new_highs,
        "new_lows": new_lows,
        "pct_above_sma20": _above_share(members, "sma20"),
        "pct_above_sma50": _above_share(members, "sma50"),
        "pct_above_sma200": _above_share(members, "sma200"),
    }


def _trend_level(pct_above_sma200: float | None) -> dict | None:
    if pct_above_sma200 is None:
        return None
    for threshold, key, label in _TREND_LEVELS:
        if pct_above_sma200 >= threshold:
            return {"key": key, "label": label}
    return None  # pragma: no cover - the last threshold is 0


def read_breadth(stats: dict, benchmark_change: float | None) -> dict:
    """One-line read of the day: does participation confirm the index's move?

    :return: ``{trend, day, note}``. ``day`` is ``broad_rally``,
        ``narrow_rally``, ``broad_selloff``, ``resilient`` (index down but most
        members up), or ``mixed`` (a flat index, or about half the members
        moving with it).
    """
    advancers_pct = stats["advancers_pct"]
    day = "mixed"
    if benchmark_change is not None and advancers_pct is not None:
        if benchmark_change >= _INDEX_MOVE_PCT:
            if advancers_pct >= 55:
                day = "broad_rally"
            elif advancers_pct < 45:
                day = "narrow_rally"
        elif benchmark_change <= -_INDEX_MOVE_PCT:
            if advancers_pct <= 45:
                day = "broad_selloff"
            elif advancers_pct >= 55:
                day = "resilient"

    notes = {
        "broad_rally": "Most members are rising with the index.",
        "narrow_rally": "The index is up, but most members are not: a narrow rally.",
        "broad_selloff": "Most members are falling with the index.",
        "resilient": "The index is down, but most members are holding up.",
        "mixed": "About half the members moved with the index.",
    }
    note = notes[day]
    if stats["new_highs"] or stats["new_lows"]:
        if stats["new_highs"] >= 2 * max(stats["new_lows"], 1):
            note += " New highs outnumber new lows."
        elif stats["new_lows"] >= 2 * max(stats["new_highs"], 1):
            note += " New lows outnumber new highs."
    return {"trend": _trend_level(stats["pct_above_sma200"]), "day": day, "note": note}


def summarize_sectors(members: list[dict]) -> list[dict]:
    """Breadth per sector, strongest share above the 50-day first."""
    by_sector: dict[str, list[dict]] = defaultdict(list)
    for member in members:
        if member["sector"]:
            by_sector[member["sector"]].append(member)
    sectors = []
    for sector, group in by_sector.items():
        counts = _counts(group)
        changes = [m["change"] for m in group if m["change"] is not None]
        sectors.append(
            {
                "sector": sector,
                "members": counts["members"],
                "advancers": counts["advancers"],
                "decliners": counts["decliners"],
                "pct_above_sma50": counts["pct_above_sma50"],
                "pct_above_sma200": counts["pct_above_sma200"],
                "new_highs": counts["new_highs"],
                "new_lows": counts["new_lows"],
                "avg_change": (
                    round(sum(changes) / len(changes), 2) if changes else None
                ),
            }
        )
    sectors.sort(key=lambda s: (-(s["pct_above_sma50"] or 0), s["sector"]))
    return sectors


def build_universe(
    key: str, label: str, benchmark: str, members: list[dict], quote: dict | None
) -> dict:
    stats = _counts(members)
    change = _num(quote.get("change")) if quote else None
    return {
        "key": key,
        "label": label,
        "benchmark": {
            "symbol": benchmark.split(":", 1)[-1],
            "price": _num(quote.get("close")) if quote else None,
            "change_pct": round(change, 2) if change is not None else None,
        },
        **stats,
        "read": read_breadth(stats, change),
    }


def session_date(now: datetime | None = None) -> str | None:
    """The NYSE session the scanner's figures belong to right now.

    The session in progress while the market is open, otherwise the last one
    that finished, so pre-market and weekend reads are filed under the session
    they describe rather than under today's date.
    """
    global _calendar
    try:
        if _calendar is None:
            _calendar = xcals.get_calendar("XNYS")
        minute = pd.Timestamp(now or datetime.now(timezone.utc))
        if minute.tzinfo is None:
            minute = minute.tz_localize("UTC")
        minute = minute.floor("min")
        if _calendar.is_open_on_minute(minute):
            return str(_calendar.minute_to_session(minute).date())
        return str(_calendar.minute_to_past_session(minute).date())
    except Exception as exc:
        logger.debug("[breadth] XNYS calendar failed: %r", exc)
        return None


async def _scan(session: aiohttp.ClientSession, payload: dict) -> list[dict] | None:
    try:
        async with session.post(_SCANNER_URL, json=payload, timeout=_TIMEOUT) as resp:
            if resp.status != 200:
                logger.warning("[breadth] scanner returned status=%s", resp.status)
                return None
            body = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        logger.warning("[breadth] scanner request failed: %r", exc)
        return None
    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, list) else None


async def _fetch() -> dict | None:
    async with aiohttp.ClientSession() as session:
        member_rows = await asyncio.gather(
            *(
                _scan(
                    session,
                    {
                        "symbols": {"symbolset": [symbolset]},
                        "columns": _COLUMNS,
                        "range": [0, _MAX_MEMBERS],
                    },
                )
                for _, _, symbolset, _ in UNIVERSES
            )
        )
        quote_rows = await _scan(
            session,
            {
                "symbols": {"tickers": [benchmark for *_, benchmark in UNIVERSES]},
                "columns": ["name", "close", "change"],
            },
        )

    quotes = {
        row.get("s"): dict(zip(["name", "close", "change"], row.get("d") or []))
        for row in quote_rows or []
        if isinstance(row, dict)
    }
    universes = []
    sectors: list[dict] = []
    for (key, label, _, benchmark), rows in zip(UNIVERSES, member_rows):
        members = [m for m in map(parse_member, rows or []) if m is not None]
        if not members:
            continue
        universes.append(
            build_universe(key, label, benchmark, members, quotes.get(benchmark))
        )
        if key == "spx":
            sectors = summarize_sectors(members)
    if not universes:
        return None
    return {
        "universes": universes,
        "sectors": sectors,
        "session_date": session_date(),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": "tradingview",
    }


async def get_market_breadth() -> dict | None:
    """Breadth for the S&P 500, Nasdaq 100 and Russell 2000, plus S&P sectors.

    :return: ``{universes, sectors, session_date, as_of, source}``, or ``None``
        when the scanner returned nothing for every index. 5-minute cache.
    """
    global _cache
    async with _lock:
        if _cache and time.time() - _cache[0] <= _CACHE_TTL:
            return _cache[1]
        data = await _fetch()
        if data is not None:
            _cache = (time.time(), data)
        return data
