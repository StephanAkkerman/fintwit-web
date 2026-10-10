"""Claude market check API: the owner's strategy and Claude's decision journal.

The dashboard's /advisor page edits the strategy and shows the journal. The
MCP server reads both, and its ``log_call`` tool is the one write it can make:
appending a call here. It cannot change the strategy or anything else.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..runtime.enricher import AssetEnricher
from ..services.advisor import (
    ACTIONS,
    CONVICTIONS,
    build_scorecard,
    normalize_symbol,
    normalize_watchlist,
    price_from_assets,
)
from .auth import api_key_dep

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/advisor", tags=["advisor"], dependencies=[Depends(api_key_dep)]
)

_enricher: AssetEnricher | None = None


def _get_enricher() -> AssetEnricher:
    global _enricher
    if _enricher is None:
        _enricher = AssetEnricher()
    return _enricher


class StrategyIn(BaseModel):
    rules: str = Field(default="", max_length=20_000)
    watchlist: list[str] = Field(default_factory=list, max_length=200)


class CallIn(BaseModel):
    symbol: str
    action: str
    reasoning: str = Field(min_length=1, max_length=4_000)
    conviction: str | None = None
    rule: str | None = Field(default=None, max_length=500)
    # Used only when the server can't price the symbol itself.
    price: float | None = Field(default=None, gt=0)


def _repo():
    from . import main as _main

    return _main.ADVISOR_REPO


@router.get("/strategy")
async def get_strategy():
    return await _repo().get_strategy()


@router.put("/strategy")
async def put_strategy(payload: StrategyIn):
    return await _repo().set_strategy(
        payload.rules.strip(), normalize_watchlist(payload.watchlist)
    )


@router.get("/calls")
async def list_calls(
    limit: int = Query(default=50, ge=1, le=500),
    symbol: str | None = Query(default=None),
    since_hours: int | None = Query(default=None, ge=1, le=24 * 365),
):
    return await _repo().list_calls(limit=limit, symbol=symbol, since_hours=since_hours)


@router.post("/calls", status_code=201)
async def create_call(payload: CallIn):
    symbol = normalize_symbol(payload.symbol)
    if symbol is None:
        raise HTTPException(status_code=422, detail="symbol is not a ticker")
    action = payload.action.strip().lower()
    if action not in ACTIONS:
        raise HTTPException(status_code=422, detail=f"action must be one of {ACTIONS}")
    conviction = (payload.conviction or "").strip().lower() or None
    if conviction is not None and conviction not in CONVICTIONS:
        raise HTTPException(
            status_code=422, detail=f"conviction must be one of {CONVICTIONS}"
        )

    # Price the call ourselves, the way the grader will re-price it, so the
    # return is measured against one consistent source.
    price, kind = None, None
    try:
        price, kind = price_from_assets(
            await _get_enricher().classify([symbol]), symbol
        )
    except Exception as exc:
        logger.warning("[advisor] pricing %s failed: %r", symbol, exc)
    if price is None:
        price = payload.price

    return await _repo().create_call(
        {
            "symbol": symbol,
            "action": action,
            "conviction": conviction,
            "price_at_call": price,
            "asset_kind": kind,
            "reasoning": payload.reasoning.strip(),
            "rule": (payload.rule or "").strip() or None,
        }
    )


@router.get("/scorecard")
async def scorecard():
    repo = _repo()
    return build_scorecard(await repo.graded_calls(), await repo.count_calls())
