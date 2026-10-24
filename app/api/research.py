"""Per-ticker research views: valuation, technicals and longer price context.

These fill what a buy or sell decision needs beyond today's move: what the
company is valued at and what analysts expect, TradingView's technical rating
and daily indicators (RSI, MACD, moving averages, ATR, ADX, volume), where the
price sits against its 52-week range and moving averages, its weekly trend
stage and strength against the market and its sector, and what analysts did
lately (rating changes, estimate revisions). The
dashboard's ticker cards show parts of this already (via tweet enrichment);
here it is available for any symbol on demand, mainly for the MCP server.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from ..services.analyst_service import get_analyst_activity
from ..services.fundamentals_service import get_valuation
from ..services.price_context import get_price_context
from ..services.technical_indicators_service import (
    MAX_SYMBOLS,
    get_indicators,
    get_symbol_indicators,
)
from ..services.tradingview_ta_service import get_tradingview_ta_summary
from ..services.trend_stage import get_trend_stage
from .auth import api_key_dep

router = APIRouter(
    prefix="/api/research", tags=["research"], dependencies=[Depends(api_key_dep)]
)


def _symbol(value: str) -> str:
    symbol = value.strip().upper()
    if not symbol or len(symbol) > 20:
        raise HTTPException(status_code=422, detail="symbol is required")
    return symbol


@router.get("/valuation")
async def valuation(symbol: str = Query(...)):
    """P/E, EPS, market cap, analyst targets and rating, and short interest."""
    symbol = _symbol(symbol)
    data = await get_valuation(symbol)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No valuation data for {symbol}")
    return data


@router.get("/technicals")
async def technicals(
    symbol: str = Query(...),
    asset_kind: str = Query(
        default="stock", pattern="^(stock|etf|crypto|forex|index)$"
    ),
):
    """TradingView's 4-hour and daily buy/neutral/sell technical summary, plus
    the daily indicators under ``indicators`` (see ``/indicators``).

    Either half may be missing (``indicators: null``, or no summary keys);
    404 only when both are.
    """
    symbol = _symbol(symbol)
    summary, indicators = await asyncio.gather(
        get_tradingview_ta_summary(symbol, asset_kind),
        get_symbol_indicators(symbol, asset_kind),
    )
    if summary is None and indicators is None:
        raise HTTPException(status_code=404, detail=f"No technicals for {symbol}")
    return {"symbol": symbol, **(summary or {}), "indicators": indicators}


@router.get("/indicators")
async def indicators(
    symbols: str = Query(..., description="Comma-separated, e.g. AAPL,EWZ,BRK-B"),
    asset_kind: str = Query(default="stock", pattern="^(stock|etf|crypto)$"),
):
    """Daily RSI(14), MACD, distance from the 20/50/200-day SMAs and their
    golden/death cross, ATR(14), ADX(14) and volume against its 30-day
    average, for up to 50 symbols in one TradingView scanner request. Symbols
    the scanner misses are computed from daily price history instead
    (``source: "price_history"``, no ratings).

    Keyed by symbol; ``null`` where neither source has data for it.
    """
    names = list(dict.fromkeys(_symbol(s) for s in symbols.split(",") if s.strip()))
    if not names:
        raise HTTPException(status_code=422, detail="symbols is required")
    if len(names) > MAX_SYMBOLS:
        raise HTTPException(
            status_code=422, detail=f"At most {MAX_SYMBOLS} symbols per request"
        )
    return await get_indicators(names, asset_kind)


@router.get("/price-context")
async def price_context(symbol: str = Query(...)):
    """52-week and all-time range, 1/3/6/12-month returns and 50/200-day SMAs."""
    symbol = _symbol(symbol)
    data = await get_price_context(symbol)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No price history for {symbol}")
    return data


@router.get("/analysts")
async def analysts(
    symbol: str = Query(...),
    days: int = Query(default=90, ge=1, le=365),
):
    """Upgrades, downgrades and price-target changes in the last ``days``,
    the buy/hold/sell mix against three months ago, and EPS estimate
    revisions (``estimates.direction``: rising, falling or flat)."""
    symbol = _symbol(symbol)
    data = await get_analyst_activity(symbol, days)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No analyst data for {symbol}")
    return data


@router.get("/trend-stage")
async def trend_stage(symbol: str = Query(...)):
    """Weinstein stage (1 basing, 2 advancing, 3 topping, 4 declining) from the
    30-week moving average, Mansfield relative strength against SPY, and the
    sector ETF's own stage and strength with the stock measured against it."""
    symbol = _symbol(symbol)
    data = await get_trend_stage(symbol)
    if data is None:
        raise HTTPException(
            status_code=404, detail=f"Not enough weekly history for {symbol}"
        )
    return data
