"""Overview API: macro strip + on-demand tweet mention analytics."""

import asyncio
import logging
import time
from collections import deque

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from ticker_price_data import get_tradingview_quote

from ..services.mention_aggregator import (
    get_activity_summary,
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

_STRIP_CACHE_TTL = 300  # seconds
_strip_cache: tuple[float, list[dict]] | None = None
_strip_lock = asyncio.Lock()

# Rolling per-label price history, one point appended per real fetch (i.e.
# once per _STRIP_CACHE_TTL). 48 points * 5min = ~4h of trend for the strip
# sparklines; in-memory only, so it resets on restart like _strip_cache.
_STRIP_HISTORY_MAXLEN = 48
_strip_history: dict[str, deque[float]] = {}


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
                history = _strip_history.setdefault(
                    label, deque(maxlen=_STRIP_HISTORY_MAXLEN)
                )
                history.append(price)
                return {
                    "label": label,
                    "symbol": symbol,
                    "price": price,
                    "change_pct": float(result.get("change_percent") or 0.0),
                    "sparkline": list(history),
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


# ─── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/macro-strip")
async def macro_strip():
    return await _get_strip()


@router.get("/activity-summary")
async def activity_summary(
    asset_kind: str = Query(default="all"),
    window_hours: int = Query(default=24, ge=1, le=168),
    user_screen_name: str | None = Query(default=None),
    subscriber_only: bool = Query(default=False),
):
    from . import main as _main

    return await get_activity_summary(
        _main.Session,
        asset_kind=asset_kind,
        window_hours=window_hours,
        user_screen_name=user_screen_name or None,
        subscriber_only=subscriber_only,
    )


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
