"""Claude market check API: the owner's strategy and Claude's decision journal.

The dashboard's /advisor page edits the strategy and shows the journal and
recent checks. The MCP server reads all of it, and can make two append-only
writes: ``log_call`` adds a call and ``finish_check`` records a finished check
(``/runs``) with the newest post it read. It cannot change the strategy or
anything else.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..runtime.enricher import AssetEnricher
from ..runtime.portfolio_valuation import resolve_holdings
from ..services.advisor import (
    ACTIONS,
    CONVICTIONS,
    build_scorecard,
    group_ticker_posts,
    normalize_screen_names,
    normalize_symbol,
    normalize_watchlist,
    price_from_assets,
)
from ..services.trader_scoring import get_credibility_batch
from .auth import api_key_dep

logger = logging.getLogger(__name__)

#: The most posts one check reads. A busy weekend can exceed it; the newest win.
MAX_UNSEEN_POSTS = 2000

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
    # None keeps the stored list, so an older client saving the form doesn't
    # wipe it.
    followed_traders: list[str] | None = Field(default=None, max_length=200)
    available_cash: float | None = Field(default=None, ge=0)
    cash_currency: str = Field(default="USD", pattern="^[A-Za-z]{3}$")


class RunIn(BaseModel):
    # The ``cursor`` that ``/unseen-posts`` returned: the newest tweet read.
    cursor: str | None = Field(default=None, pattern=r"^\d{1,20}$")
    summary: str = Field(default="", max_length=4_000)
    session: str | None = Field(default=None, max_length=40)
    posts_read: int | None = Field(default=None, ge=0)


class CallIn(BaseModel):
    symbol: str
    action: str
    reasoning: str = Field(min_length=1, max_length=4_000)
    conviction: str | None = None
    rule: str | None = Field(default=None, max_length=500)
    # Used only when the server can't price the symbol itself.
    price: float | None = Field(default=None, gt=0)


def _main():
    from . import main

    return main


def _repo():
    return _main().ADVISOR_REPO


@router.get("/strategy")
async def get_strategy():
    return await _repo().get_strategy()


@router.put("/strategy")
async def put_strategy(payload: StrategyIn):
    return await _repo().set_strategy(
        payload.rules.strip(),
        normalize_watchlist(payload.watchlist),
        payload.available_cash,
        payload.cash_currency.upper(),
        None
        if payload.followed_traders is None
        else normalize_screen_names(payload.followed_traders),
    )


@router.get("/followed-mentions")
async def followed_mentions(
    since_hours: int = Query(default=24, ge=1, le=24 * 30),
    limit: int = Query(default=25, ge=1, le=100),
):
    """Tickers the owner's followed traders posted about, one lead per ticker.

    These are leads, not verdicts: the market check vets each one against
    fundamentals and technicals before suggesting anything.
    """
    strategy = await _repo().get_strategy()
    traders = strategy["followed_traders"]
    if not traders:
        return {"traders": [], "since_hours": since_hours, "leads": []}

    tweets = await _repo().tweets_by_authors(traders, since_hours)
    leads = group_ticker_posts(tweets, await _held_symbols(), traders)[:limit]
    track_record = await _track_records(traders)
    return {
        "traders": [
            {"screen_name": name, "track_record_7d": track_record.get(name)}
            for name in traders
        ],
        "since_hours": since_hours,
        "leads": leads,
    }


async def _held_symbols() -> set[str]:
    """What the owner holds, from IBKR when it is synced, else the manual list
    (the same choice ``/api/portfolio/insights`` makes)."""
    main = _main()
    _, holdings = await resolve_holdings(main.PORTFOLIO_REPO, main.IBKR_REPO)
    return {str(h.get("symbol") or "").upper() for h in holdings}


async def _track_records(names: list[str]) -> dict[str, dict]:
    try:
        return await get_credibility_batch(_main().Session, names)
    except Exception as exc:
        logger.warning("[advisor] trader credibility lookup failed: %r", exc)
        return {}


@router.get("/unseen-posts")
async def unseen_posts(
    limit: int = Query(default=40, ge=1, le=200),
    first_run_hours: int = Query(default=12, ge=1, le=24 * 7),
):
    """Every post since the last finished check, grouped into one lead per
    ticker, so a scheduled check reads the timeline the way the owner would.

    The first check (no run recorded yet) reads the last ``first_run_hours``.
    Pass the returned ``cursor`` to ``POST /runs`` when the check is done, so
    the next one starts after it.
    """
    repo = _repo()
    previous = await repo.last_cursor()
    tweets = await repo.tweets_after(previous, first_run_hours, MAX_UNSEEN_POSTS)
    with_tickers = [t for t in tweets if t.get("tickers")]
    strategy = await repo.get_strategy()
    followed = strategy["followed_traders"]
    leads = group_ticker_posts(with_tickers, await _held_symbols(), followed)[:limit]

    authors = sorted({name.lower() for lead in leads for name in lead["traders"]})
    records = await _track_records(authors)
    # Unchanged when nothing new came in, so the next check starts at the
    # same place.
    cursor = max((int(t["id"]) for t in tweets), default=previous)
    return {
        "previous_cursor": None if previous is None else str(previous),
        "cursor": None if cursor is None else str(cursor),
        "posts": len(tweets),
        "posts_with_tickers": len(with_tickers),
        # One read is capped; when it is hit, posts older than the oldest one
        # here were skipped.
        "truncated": len(tweets) >= MAX_UNSEEN_POSTS,
        "followed_traders": followed,
        "track_records_7d": records,
        "tickers": len({lead["symbol"] for lead in leads}),
        "leads": leads,
    }


@router.get("/runs")
async def list_runs(limit: int = Query(default=20, ge=1, le=200)):
    return await _repo().list_runs(limit)


@router.post("/runs", status_code=201)
async def record_run(payload: RunIn):
    return await _repo().record_run(
        None if payload.cursor is None else int(payload.cursor),
        payload.summary.strip(),
        (payload.session or "").strip() or None,
        payload.posts_read,
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
