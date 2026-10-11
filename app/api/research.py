"""Per-ticker research views: valuation, technicals and longer price context.

These fill what a buy or sell decision needs beyond today's move: what the
company is valued at and what analysts expect, TradingView's technical rating,
and where the price sits against its 52-week range and moving averages. The
dashboard's ticker cards show parts of this already (via tweet enrichment);
here it is available for any symbol on demand, mainly for the MCP server.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..services.fundamentals_service import get_valuation
from ..services.price_context import get_price_context
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
    """TradingView's 4-hour and daily buy/neutral/sell technical summary."""
    symbol = _symbol(symbol)
    data = await get_tradingview_ta_summary(symbol, asset_kind)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No technicals for {symbol}")
    return data


@router.get("/price-context")
async def price_context(symbol: str = Query(...)):
    """52-week and all-time range, 1/3/6/12-month returns and 50/200-day SMAs."""
    symbol = _symbol(symbol)
    data = await get_price_context(symbol)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No price history for {symbol}")
    return data
