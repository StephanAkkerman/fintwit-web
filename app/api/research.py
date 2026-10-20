"""Per-ticker research views: valuation, technicals and longer price context.

These fill what a buy or sell decision needs beyond today's move: what the
company is valued at and what analysts expect, TradingView's technical rating
and daily indicators (RSI, MACD, moving averages, ATR, ADX, volume), and where the price sits against its 52-week range and moving averages. The
dashboard's ticker cards show parts of this already (via tweet enrichment);
here it is available for any symbol on demand, mainly for the MCP server.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from ..services.fundamentals_service import get_valuation
from ..services.price_context import get_price_context
from ..services.technical_indicators_service import (
    MAX_SYMBOLS,
    get_indicators,
    get_symbol_indicators,
)
from ..services.tradingview_ta_service import get_tradingview_ta_summary
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
    average, for up to 50 symbols in one TradingView scanner request.

    Keyed by symbol; ``null`` where TradingView has no data for it.
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
