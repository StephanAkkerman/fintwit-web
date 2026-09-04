"""Trader credibility API: leaderboard + per-trader accuracy detail."""

from fastapi import APIRouter, HTTPException, Query

from ..services.trader_scoring import HORIZONS, get_leaderboard, get_trader_detail

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
async def trader_detail(screen_name: str):
    from . import main as _main

    return await get_trader_detail(_main.Session, screen_name)
