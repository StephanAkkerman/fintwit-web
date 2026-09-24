"""Overview API: macro strip + on-demand tweet mention analytics."""

import asyncio
import logging
import time

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from ticker_price_data import get_price_history, get_tradingview_quote

from ..services.mention_aggregator import (
    get_hidden_gems,
    get_mention_frequency,
    get_mention_heat,
    get_sector_mentions,
    get_sentiment_shift,
    get_ticker_timeseries,
    get_volume_baseline,
)

router = APIRouter(prefix="/api/overview", tags=["overview"])
logger = logging.getLogger(__name__)

# ─── Macro strip ────────────────────────────────────────────────────────────

_STRIP_TICKERS: list[tuple[str, str, str]] = [
    ("SPX", "TVC:SPX", "index"),
    ("NDX", "IG:NASDAQ", "index"),
    ("BTC", "BITSTAMP:BTCUSD", "crypto"),
    ("ETH", "BITSTAMP:ETHUSD", "crypto"),
    ("DXY", "TVC:DXY", "forex"),
    ("VIX", "TVC:VIX", "index"),
    ("GOLD", "TVC:GOLD", "index"),
]

# Yahoo Finance symbols for the sparkline series, keyed by strip label. Kept
# separate from the TradingView symbols above (used for the live price/%
# change) since Yahoo's lookup namespace differs; SPX/DXY/VIX are plain
# labels because ticker_price_data.get_price_history already maps those to
# their real Yahoo symbols internally.
_STRIP_YAHOO_SYMBOLS: dict[str, str] = {
    "SPX": "SPX",
    "NDX": "^NDX",
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "DXY": "DXY",
    "VIX": "VIX",
    "GOLD": "GC=F",
}

_STRIP_CACHE_TTL = 300  # seconds
_strip_cache: tuple[float, list[dict]] | None = None
_strip_lock = asyncio.Lock()


async def _fetch_sparkline(label: str) -> list[float]:
    yahoo_symbol = _STRIP_YAHOO_SYMBOLS.get(label)
    if not yahoo_symbol:
        return []
    try:
        history = await get_price_history(yahoo_symbol, range_="1d", interval="5m")
    except Exception as exc:
        logger.debug("[macro-strip] history for %s failed: %r", label, exc)
        return []
    if not history:
        return []
    return [point["close"] for point in history]


async def _build_strip() -> list[dict]:
    sem = asyncio.Semaphore(4)

    async def _fetch(label: str, symbol: str, hint: str) -> dict | None:
        async with sem:
            try:
                result = await get_tradingview_quote(symbol, asset_hint=hint)
                if not isinstance(result, dict):
                    return None
                price = result.get("price")
                if not isinstance(price, (int, float)):
                    return None
                price = float(price)
                return {
                    "label": label,
                    "symbol": symbol,
                    "price": price,
                    "change_pct": float(result.get("change_percent") or 0.0),
                    "sparkline": await _fetch_sparkline(label),
                }
            except Exception as exc:
                logger.debug("[macro-strip] %s failed: %r", symbol, exc)
                return None

    results = await asyncio.gather(
        *[_fetch(label, symbol, hint) for label, symbol, hint in _STRIP_TICKERS]
    )
    return [r for r in results if r is not None]


async def _get_strip() -> list[dict]:
    global _strip_cache
    async with _strip_lock:
        if _strip_cache is not None:
            ts, payload = _strip_cache
            if time.time() - ts < _STRIP_CACHE_TTL:
                return payload
        payload = await _build_strip()
        _strip_cache = (time.time(), payload)
        return payload


# ─── Per-ticker daily price chart ──────────────────────────────────────────
# Powers the price chart in TickerDetailModal (opened by clicking a ticker
# in a post). Separate from the macro strip above: fetched lazily per ticker
# on modal open rather than polled for a fixed watchlist, so it takes an
# arbitrary symbol and doesn't know its asset kind up front.

_TICKER_HISTORY_CACHE_TTL = 60  # seconds
_ticker_history_cache: dict[str, tuple[float, list[dict]]] = {}
_ticker_history_lock = asyncio.Lock()


async def _fetch_ticker_history(ticker: str) -> list[dict]:
    # Try the ticker as a Yahoo symbol directly (stocks, indices, forex), then
    # as "<ticker>-USD" (crypto) — mirrors ticker_price_data.coingecko's own
    # Yahoo fallback, without needing a classifier call just to pick a route.
    for candidate in (ticker, f"{ticker}-USD"):
        try:
            history = await get_price_history(candidate, range_="1d", interval="5m")
        except Exception as exc:
            logger.debug("[ticker-price-history] %s failed: %r", candidate, exc)
            continue
        if history:
            return history
    return []


async def _get_ticker_history(ticker: str) -> list[dict]:
    now = time.time()
    async with _ticker_history_lock:
        cached = _ticker_history_cache.get(ticker)
        if cached and now - cached[0] < _TICKER_HISTORY_CACHE_TTL:
            return cached[1]

    points = await _fetch_ticker_history(ticker)

    async with _ticker_history_lock:
        _ticker_history_cache[ticker] = (time.time(), points)
    return points


# ─── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/macro-strip")
async def macro_strip():
    return await _get_strip()


@router.get("/mention-heat")
async def mention_heat(
    asset_kind: str = Query(default="all"),
    window_hours: int = Query(default=24, ge=1, le=168),
    user_screen_name: str | None = Query(default=None),
    subscriber_only: bool = Query(default=False),
):
    from . import main as _main

    return await get_mention_heat(
        _main.Session,
        asset_kind=asset_kind,
        window_hours=window_hours,
        user_screen_name=user_screen_name or None,
        subscriber_only=subscriber_only,
    )


@router.get("/sentiment-shift")
async def sentiment_shift(
    asset_kind: str = Query(default="all"),
    window_hours: int = Query(default=24, ge=1, le=168),
    user_screen_name: str | None = Query(default=None),
    subscriber_only: bool = Query(default=False),
):
    from . import main as _main

    return await get_sentiment_shift(
        _main.Session,
        asset_kind=asset_kind,
        window_hours=window_hours,
        user_screen_name=user_screen_name or None,
        subscriber_only=subscriber_only,
    )


@router.get("/volume-baseline")
async def volume_baseline(
    asset_kind: str = Query(default="all"),
    window_hours: int = Query(default=24, ge=1, le=168),
    user_screen_name: str | None = Query(default=None),
    subscriber_only: bool = Query(default=False),
):
    from . import main as _main

    return await get_volume_baseline(
        _main.Session,
        asset_kind=asset_kind,
        window_hours=window_hours,
        user_screen_name=user_screen_name or None,
        subscriber_only=subscriber_only,
    )


class MentionFrequencyRequestItem(BaseModel):
    author: str
    tickers: list[str] = Field(default_factory=list)


class MentionFrequencyRequest(BaseModel):
    # Cap the batch so a malformed/huge feed can't trigger an unbounded scan.
    requests: list[MentionFrequencyRequestItem] = Field(
        default_factory=list, max_length=300
    )


@router.post("/mention-frequency")
async def mention_frequency(payload: MentionFrequencyRequest):
    from . import main as _main

    return await get_mention_frequency(
        _main.Session,
        requests=[r.model_dump() for r in payload.requests],
    )


@router.get("/ticker-timeseries")
async def ticker_timeseries(
    ticker: str = Query(...),
    window_hours: int = Query(default=168, ge=1, le=720),
    user_screen_name: str | None = Query(default=None),
    subscriber_only: bool = Query(default=False),
):
    from . import main as _main

    ticker = ticker.strip()
    if not ticker:
        raise HTTPException(status_code=422, detail="ticker is required")

    return await get_ticker_timeseries(
        _main.Session,
        ticker=ticker,
        window_hours=window_hours,
        user_screen_name=user_screen_name or None,
        subscriber_only=subscriber_only,
    )


@router.get("/ticker-price-history")
async def ticker_price_history(ticker: str = Query(...)):
    """Today's intraday price series for a single ticker (5-min closes).

    Powers the price chart in the ticker detail modal opened from a post.
    """
    ticker = ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=422, detail="ticker is required")

    return {"ticker": ticker, "points": await _get_ticker_history(ticker)}


@router.get("/sector-mentions")
async def sector_mentions(
    window_hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=15, ge=1, le=50),
    user_screen_name: str | None = Query(default=None),
    subscriber_only: bool = Query(default=False),
):
    from . import main as _main

    return await get_sector_mentions(
        _main.Session,
        window_hours=window_hours,
        limit=limit,
        user_screen_name=user_screen_name or None,
        subscriber_only=subscriber_only,
    )


@router.get("/hidden-gems")
async def hidden_gems(
    asset_kind: str = Query(default="all"),
    window_hours: int = Query(default=24, ge=1, le=168),
    user_screen_name: str | None = Query(default=None),
    subscriber_only: bool = Query(default=False),
):
    from . import main as _main

    return await get_hidden_gems(
        _main.Session,
        asset_kind=asset_kind,
        window_hours=window_hours,
        user_screen_name=user_screen_name or None,
        subscriber_only=subscriber_only,
    )
