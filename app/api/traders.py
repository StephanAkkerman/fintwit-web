"""Trader credibility API: leaderboard + per-trader accuracy detail."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.trader_scoring import (
    HORIZONS,
    get_credibility_batch,
    get_leaderboard,
    get_trader_detail,
)

router = APIRouter(prefix="/api/traders", tags=["traders"])


def _validate_horizon(horizon_days: int) -> None:
    if horizon_days not in HORIZONS:
        raise HTTPException(
            status_code=422,
            detail=f"horizon_days must be one of {HORIZONS}",
        )


@router.get("/leaderboard")
async def leaderboard(
    horizon_days: int = Query(default=7),
    min_calls: int = Query(default=5, ge=1, le=1000),
    limit: int = Query(default=25, ge=1, le=100),
):
    _validate_horizon(horizon_days)
    from . import main as _main

    return await get_leaderboard(
        _main.Session,
        horizon_days=horizon_days,
        min_calls=min_calls,
        limit=limit,
    )


@router.get("/user/{screen_name}")
async def trader_detail(
    screen_name: str,
    horizon_days: int = Query(default=7),
    limit: int = Query(default=50, ge=1, le=200),
):
    _validate_horizon(horizon_days)
    from . import main as _main

    return await get_trader_detail(
        _main.Session,
        screen_name,
        horizon_days=horizon_days,
        recent_limit=limit,
    )


class CredibilityBatchRequest(BaseModel):
    # Cap the batch so a malformed/huge feed can't trigger an unbounded scan.
    screen_names: list[str] = Field(default_factory=list, max_length=300)
    horizon_days: int = 7


@router.post("/credibility")
async def credibility_batch(payload: CredibilityBatchRequest):
    _validate_horizon(payload.horizon_days)
    from . import main as _main

    return await get_credibility_batch(
        _main.Session,
        screen_names=payload.screen_names,
        horizon_days=payload.horizon_days,
    )
