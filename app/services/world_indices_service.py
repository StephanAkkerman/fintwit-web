"""Overseas stock indices to read the US open from (issue #218).

Asia trades while New York sleeps and Europe overlaps the US pre-market, so
their moves are the first hint of how US stocks will open: a KOSPI sell-off
lands on memory names, a weak TAIEX on the TSMC supply chain. Each row pairs
a TradingView quote with that exchange's session state from
``exchange_calendars`` (offline), so a stale change from a closed or holiday
market is labelled with the session it belongs to. US index futures close the
list as the live read of where the cash open is heading.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from statistics import mean
from typing import Optional

import exchange_calendars as xcals
import pandas as pd
from ticker_price_data import get_tradingview_quote

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300
# The quotes go through TradingView's shared websocket; a few at a time keeps
# it from timing out symbols the way a burst of 20 does.
_QUOTE_CONCURRENCY = 4
_cache: tuple[float, Optional[dict]] | None = None
_cache_lock = asyncio.Lock()
_calendars: dict[str, xcals.ExchangeCalendar] = {}

# A move this large across the chip-heavy indices is worth calling out.
_SEMIS_SIGNAL_THRESHOLD = 1.0

# (symbol, name, country, region, tradingview symbol, xcals calendar, tz, read-through, tags)
WORLD_INDICES: list[tuple[str, str, str, str, str, str | None, str, str, tuple]] = [
    (
        "NI225",
        "Nikkei 225",
        "JP",
        "asia",
        "TVC:NI225",
        "XTKS",
        "Asia/Tokyo",
        "Tokyo Electron, Advantest: chip equipment; yen moves",
        ("semis",),
    ),
    (
        "KOSPI",
        "KOSPI",
        "KR",
        "asia",
        "KRX:KOSPI",
        "XKRX",
        "Asia/Seoul",
        "Samsung, SK Hynix: memory (MU, SNDK, WDC)",
        ("semis",),
    ),
    (
        "TAIEX",
        "TAIEX",
        "TW",
        "asia",
        "TWSE:TAIEX",
        "XTAI",
        "Asia/Taipei",
        "TSMC supply chain (TSM, NVDA, AMD, AAPL)",
        ("semis",),
    ),
    (
        "HSI",
        "Hang Seng",
        "HK",
        "asia",
        "TVC:HSI",
        "XHKG",
        "Asia/Hong_Kong",
        "China tech ADRs (BABA, JD, PDD, BIDU)",
        (),
    ),
    (
        "SHCOMP",
        "Shanghai Composite",
        "CN",
        "asia",
        "SSE:000001",
        "XSHG",
        "Asia/Shanghai",
        "China demand: copper, steel, luxury",
        (),
    ),
    (
        "XJO",
        "ASX 200",
        "AU",
        "asia",
        "ASX:XJO",
        "XASX",
        "Australia/Sydney",
        "Miners and banks: commodities (BHP, RIO, FCX)",
        (),
    ),
    (
        "NIFTY",
        "Nifty 50",
        "IN",
        "asia",
        "NSE:NIFTY",
        "XBOM",
        "Asia/Kolkata",
        "India ADRs (INFY, HDB, IBN)",
        (),
    ),
    (
        "DAX",
        "DAX",
        "DE",
        "europe",
        "XETR:DAX",
        "XETR",
        "Europe/Berlin",
        "Autos, industrials, SAP",
        (),
    ),
    (
        "UKX",
        "FTSE 100",
        "GB",
        "europe",
        "TVC:UKX",
        "XLON",
        "Europe/London",
        "Oil majors, miners, banks",
        (),
    ),
    (
        "PX1",
        "CAC 40",
        "FR",
        "europe",
        "EURONEXT:PX1",
        "XPAR",
        "Europe/Paris",
        "Luxury (LVMH, Hermès), aerospace",
        (),
    ),
    (
        "AEX",
        "AEX",
        "NL",
        "europe",
        "EURONEXT:AEX",
        "XAMS",
        "Europe/Amsterdam",
        "ASML, ASM International: chip equipment",
        ("semis",),
    ),
    (
        "SMI",
        "SMI",
        "CH",
        "europe",
        "SIX:SMI",
        "XSWX",
        "Europe/Zurich",
        "Pharma (Novartis, Roche), Nestlé",
        (),
    ),
    (
        "SX5E",
        "Euro Stoxx 50",
        "EU",
        "europe",
        "TVC:SX5E",
        "XETR",
        "Europe/Berlin",
        "Eurozone large caps",
        (),
    ),
    (
        "ES",
        "S&P 500 futures",
        "US",
        "us_futures",
        "CME_MINI:ES1!",
        None,
        "America/Chicago",
        "Where the S&P 500 is set to open",
        (),
    ),
    (
        "NQ",
        "Nasdaq 100 futures",
        "US",
        "us_futures",
        "CME_MINI:NQ1!",
        None,
        "America/Chicago",
        "Where the Nasdaq 100 is set to open",
        (),
    ),
    (
        "YM",
        "Dow futures",
        "US",
        "us_futures",
        "CBOT_MINI:YM1!",
        None,
        "America/Chicago",
        "Where the Dow is set to open",
        (),
    ),
    (
        "RTY",
        "Russell 2000 futures",
        "US",
        "us_futures",
        "CME_MINI:RTY1!",
        None,
        "America/Chicago",
        "Where small caps are set to open",
        (),
    ),
]

REGIONS: list[tuple[str, str]] = [
    ("asia", "Asia-Pacific"),
    ("europe", "Europe"),
    ("us_futures", "US futures"),
]


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _get_calendar(name: str) -> xcals.ExchangeCalendar:
    if name not in _calendars:
        _calendars[name] = xcals.get_calendar(name)
    return _calendars[name]


def _session_state(calendar_name: str, now: pd.Timestamp) -> dict:
    """Whether the exchange is open, and which session its last change belongs to."""
    cal = _get_calendar(calendar_name)
    is_open = False
    session_date: str | None = None
    next_open: str | None = None
    try:
        is_open = bool(cal.is_open_on_minute(now))
        if is_open:
            session_date = str(cal.minute_to_session(now).date())
        else:
            session_date = str(cal.minute_to_past_session(now).date())
            next_open = cal.next_open(now).isoformat()
    except Exception as exc:
        logger.debug("[world_indices] calendar %s failed: %r", calendar_name, exc)
    return {"is_open": is_open, "session_date": session_date, "next_open": next_open}


def _futures_state(quote: dict) -> dict:
    # CME futures trade nearly around the clock; TradingView reports the session.
    session = str(quote.get("session") or "")
    return {
        "is_open": session in {"regular", "pre", "post"} if session else None,
        "session_date": None,
        "next_open": None,
    }


async def _fetch_quotes() -> list[Optional[dict]]:
    semaphore = asyncio.Semaphore(_QUOTE_CONCURRENCY)

    async def _one(tv_symbol: str) -> Optional[dict]:
        async with semaphore:
            try:
                return await get_tradingview_quote(
                    tv_symbol, asset_hint="index", prefer_realtime=True
                )
            except Exception as exc:
                logger.debug("[world_indices] quote failed for %s: %r", tv_symbol, exc)
                return None

    return await asyncio.gather(*[_one(row[4]) for row in WORLD_INDICES])


def _semis_read(rows: list[dict]) -> Optional[dict]:
    """Average move of the chip-heavy indices, as a read-through for US semis."""
    members = [
        row
        for row in rows
        if "semis" in row["tags"] and isinstance(row["change_percent"], (int, float))
    ]
    if not members:
        return None
    avg = round(mean(float(row["change_percent"]) for row in members), 2)
    if avg <= -_SEMIS_SIGNAL_THRESHOLD:
        tone = "bearish"
    elif avg >= _SEMIS_SIGNAL_THRESHOLD:
        tone = "bullish"
    else:
        tone = "neutral"
    return {
        "avg_change_percent": avg,
        "tone": tone,
        "symbols": [row["symbol"] for row in members],
    }


async def _build_snapshot() -> Optional[dict]:
    now = _now_utc()
    quotes = await _fetch_quotes()

    rows: list[dict] = []
    for spec, quote in zip(WORLD_INDICES, quotes):
        symbol, name, country, region, tv_symbol, cal_name, tz, read, tags = spec
        if not isinstance(quote, dict):
            continue
        price = quote.get("price")
        if not isinstance(price, (int, float)):
            continue
        change = quote.get("change_percent")
        state = _session_state(cal_name, now) if cal_name else _futures_state(quote)
        rows.append(
            {
                "symbol": symbol,
                "name": name,
                "country": country,
                "region": region,
                "price": float(price),
                "change_percent": (
                    float(change) if isinstance(change, (int, float)) else None
                ),
                "timezone": tz,
                "read_through": read,
                "tags": list(tags),
                "tv_symbol": tv_symbol,
                "website": quote.get("website"),
                **state,
            }
        )

    if not rows:
        return None

    regions = []
    for key, label in REGIONS:
        members = [row for row in rows if row["region"] == key]
        if not members:
            continue
        changes = [
            row["change_percent"]
            for row in members
            if isinstance(row["change_percent"], (int, float))
        ]
        regions.append(
            {
                "key": key,
                "label": label,
                "avg_change_percent": round(mean(changes), 2) if changes else None,
                "indices": members,
            }
        )

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "regions": regions,
        "semis": _semis_read(rows),
        "source": "tradingview",
    }


async def get_world_indices() -> Optional[dict]:
    """Return overseas index moves grouped by region, cached for five minutes."""
    global _cache
    async with _cache_lock:
        if _cache is not None and time.time() - _cache[0] < _CACHE_TTL_SECONDS:
            return _cache[1]
        payload = await _build_snapshot()
        # Don't pin a total outage for the full TTL; retry on the next request.
        if payload is not None:
            _cache = (time.time(), payload)
        return payload


def _reset_cache_for_tests() -> None:
    global _cache
    _cache = None


if __name__ == "__main__":
    import json

    print(json.dumps(asyncio.run(get_world_indices()), indent=2))
