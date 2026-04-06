# app/api/main.py (updated bits)
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..infra.db import create_engine, init_db
from ..infra.repos import PortfolioRepo, TweetRepo
from ..ml.sentiment import FinTwitSentiment
from ..runtime.broadcast import Broadcaster
from ..runtime.enricher import AssetEnricher
from ..runtime.streamer import run_stream
from ..runtime.symbols import merge_symbols
from ..services.cmc import get_trending_crypto
from ..services.coin360_service import get_treemap_data
from ..services.fear_greed_service import get_feargreed
from ..services.stocktwits_service import get_stocktwits_data
from ..services.unusual_whales import get_spy_heatmap
from ..services.yahoo import get_stock_info

ENGINE = create_engine(os.getenv("DB_URL", "sqlite+aiosqlite:///./data.db"))
Session = async_sessionmaker(ENGINE, expire_on_commit=False)
REPO = TweetRepo(Session)
PORTFOLIO_REPO = PortfolioRepo(Session)
BROADCAST = Broadcaster()
logger = logging.getLogger(__name__)


async def api_key_dep(request: Request):
    expected = getattr(request.app.state, "API_KEY", "")
    got = request.headers.get("X-API-Key")
    if expected and got != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(ENGINE)
    app.state.API_KEY = os.getenv("API_KEY", "")
    app.state.http_client = httpx.AsyncClient()

    sentiment_model: FinTwitSentiment | None = FinTwitSentiment()
    try:
        await sentiment_model.warmup()
    except Exception as exc:
        logger.warning("[startup] sentiment model warmup failed: %r", exc)
        sentiment_model = None

    app.state.sentiment_model = sentiment_model

    # start background stream: persist THEN broadcast
    task = asyncio.create_task(run_stream(REPO, BROADCAST, sentiment_model))
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await app.state.http_client.aclose()


app = FastAPI(title="X Stream API", lifespan=lifespan)


@app.get("/api/posts")
async def list_posts(limit: int = Query(50, ge=1, le=200), _=Depends(api_key_dep)):
    return await REPO.latest(limit)


@app.get("/api/stream")
async def stream(_=Depends(api_key_dep)):
    async def gen():
        q = await BROADCAST.subscribe()
        try:
            while True:
                item = await q.get()
                yield f"data: {json.dumps(item, default=str)}\n\n"
        finally:
            await BROADCAST.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/fear-greed")
async def fear_greed(_=Depends(api_key_dep)):
    data = await get_feargreed()
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/stocktwits")
async def stocktwits(
    request: Request, keyword: str = Query("ts"), _=Depends(api_key_dep)
):
    if keyword not in ["ts", "m_day", "wl_ct_day"]:
        raise HTTPException(status_code=400, detail="Invalid keyword")
    client: httpx.AsyncClient = request.app.state.http_client
    data = await get_stocktwits_data(client, keyword)
    if data is None:
        # StockTwits can intermittently block requests; return empty payload to avoid UI hard-fail.
        return []
    return data


@app.get("/api/spy-heatmap")
async def spy_heatmap(
    request: Request,
    date: str = Query(
        "one_day",
        enum=[
            "one_day",
            "after_hours",
            "yesterday",
            "one_week",
            "one_month",
            "ytd",
            "one_year",
        ],
    ),
    _=Depends(api_key_dep),
):
    client: httpx.AsyncClient = request.app.state.http_client
    data = await get_spy_heatmap(client, date=date)
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/treemap")
async def treemap(request: Request, _=Depends(api_key_dep)):
    client: httpx.AsyncClient = request.app.state.http_client
    data = await get_treemap_data(client)
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


class DebugTweet(BaseModel):
    text: str = "Test tweet"
    user_name: str = "Debug User"
    user_screen_name: str = "debuguser"
    user_img: str = ""
    tickers: list[str] = []
    hashtags: list[str] = []
    media: list[str] = []
    media_types: list[str] = []
    title: str = ""


class PortfolioPositionCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    quantity: float = Field(gt=0)
    avg_cost: float = Field(ge=0)
    broker: Literal["IBKR"] = "IBKR"
    currency: str = Field(default="USD", min_length=1, max_length=8)
    opened_at: datetime | None = None
    notes: str | None = None
    is_active: bool = True


class PortfolioPositionUpdate(BaseModel):
    symbol: str | None = Field(default=None, min_length=1, max_length=16)
    quantity: float | None = Field(default=None, gt=0)
    avg_cost: float | None = Field(default=None, ge=0)
    broker: Literal["IBKR"] | None = None
    currency: str | None = Field(default=None, min_length=1, max_length=8)
    opened_at: datetime | None = None
    notes: str | None = None
    is_active: bool | None = None


def _normalize_portfolio_payload(payload: dict) -> dict:
    normalized = dict(payload)

    if "symbol" in normalized and normalized["symbol"] is not None:
        normalized["symbol"] = str(normalized["symbol"]).strip().upper()

    if "currency" in normalized and normalized["currency"] is not None:
        normalized["currency"] = str(normalized["currency"]).strip().upper()

    return normalized


@app.post("/api/debug/tweet")
async def debug_tweet(body: DebugTweet, request: Request):
    tickers, hashtags = merge_symbols(body.text, body.tickers, body.hashtags)
    symbols = tickers + hashtags
    assets = []
    if symbols:
        enricher = AssetEnricher()
        assets = await enricher.classify(symbols)

    main_sentiment = None
    quoted_sentiment = None
    sentiment_model = getattr(request.app.state, "sentiment_model", None)
    if sentiment_model is not None and body.text.strip():
        try:
            sentiment_parts = await sentiment_model.classify_parts(body.text)
            main_sentiment = sentiment_parts.get("main")
            quoted_sentiment = sentiment_parts.get("quoted")
        except Exception as exc:
            logger.warning("[debug-tweet] sentiment classification failed: %r", exc)

    tweet = {
        **body.model_dump(),
        "tickers": tickers,
        "hashtags": hashtags,
        "id": int(datetime.now(timezone.utc).timestamp() * 1000),
        "url": "",
        "created_at": datetime.now(timezone.utc),
        "assets": assets,
        "replies": 0,
        "likes": 0,
        "views": 0,
        "retweets": 0,
        "sentiment_label": main_sentiment["label"] if main_sentiment else None,
        "sentiment_emoji": main_sentiment["emoji"] if main_sentiment else None,
        "sentiment_score": main_sentiment["score"] if main_sentiment else None,
        "quoted_sentiment_label": (
            quoted_sentiment["label"] if quoted_sentiment else None
        ),
        "quoted_sentiment_emoji": (
            quoted_sentiment["emoji"] if quoted_sentiment else None
        ),
        "quoted_sentiment_score": (
            quoted_sentiment["score"] if quoted_sentiment else None
        ),
    }
    await REPO.upsert_many([tweet])
    await BROADCAST.publish(tweet)
    return tweet


@app.get("/api/portfolio/positions")
async def list_portfolio_positions(
    active_only: bool | None = Query(default=None), _=Depends(api_key_dep)
):
    return await PORTFOLIO_REPO.list_positions(active_only=active_only)


@app.post("/api/portfolio/positions")
async def create_portfolio_position(
    body: PortfolioPositionCreate, _=Depends(api_key_dep)
):
    payload = _normalize_portfolio_payload(body.model_dump())
    return await PORTFOLIO_REPO.create_position(payload)


@app.patch("/api/portfolio/positions/{position_id}")
async def update_portfolio_position(
    position_id: int, body: PortfolioPositionUpdate, _=Depends(api_key_dep)
):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        current = await PORTFOLIO_REPO.by_id(position_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Position not found")
        return current

    normalized_updates = _normalize_portfolio_payload(updates)
    updated = await PORTFOLIO_REPO.update_position(position_id, normalized_updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Position not found")
    return updated


@app.delete("/api/portfolio/positions/{position_id}")
async def delete_portfolio_position(position_id: int, _=Depends(api_key_dep)):
    deleted = await PORTFOLIO_REPO.delete_position(position_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Position not found")
    return {"ok": True, "id": position_id}


@app.get("/api/portfolio/summary")
async def portfolio_summary(_=Depends(api_key_dep)):
    positions = await PORTFOLIO_REPO.list_positions(active_only=True)
    if not positions:
        return {
            "totals": {
                "positions": 0,
                "market_value": 0.0,
                "cost_basis": 0.0,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_percent": 0.0,
            },
            "positions": [],
        }

    quote_tasks = [get_stock_info(p["symbol"]) for p in positions]
    quote_results = await asyncio.gather(*quote_tasks, return_exceptions=True)

    enriched_positions: list[dict] = []
    total_market_value = 0.0
    total_cost_basis = 0.0

    for pos, quote in zip(positions, quote_results):
        quote_data = quote if isinstance(quote, dict) else None
        market_price = quote_data.get("price") if quote_data else None

        qty = float(pos["quantity"])
        avg_cost = float(pos["avg_cost"])
        cost_basis = qty * avg_cost
        market_value = qty * (
            float(market_price) if market_price is not None else avg_cost
        )
        unrealized_pnl = market_value - cost_basis
        unrealized_pnl_percent = (
            (unrealized_pnl / cost_basis * 100) if cost_basis else 0.0
        )

        total_market_value += market_value
        total_cost_basis += cost_basis

        enriched_positions.append(
            {
                **pos,
                "market_price": (
                    float(market_price) if market_price is not None else None
                ),
                "market_value": market_value,
                "cost_basis": cost_basis,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_percent": unrealized_pnl_percent,
                "website": quote_data.get("website") if quote_data else None,
            }
        )

    total_pnl = total_market_value - total_cost_basis
    total_pnl_pct = (total_pnl / total_cost_basis * 100) if total_cost_basis else 0.0

    return {
        "totals": {
            "positions": len(enriched_positions),
            "market_value": total_market_value,
            "cost_basis": total_cost_basis,
            "unrealized_pnl": total_pnl,
            "unrealized_pnl_percent": total_pnl_pct,
        },
        "positions": enriched_positions,
    }


@app.get("/api/trending-crypto")
async def trending_crypto(_=Depends(api_key_dep)):
    data = await get_trending_crypto()
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data
