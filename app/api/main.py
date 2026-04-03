# app/api/main.py (updated bits)
import asyncio
import json
import os
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..infra.db import create_engine, init_db
from ..infra.repos import TweetRepo
from ..runtime.broadcast import Broadcaster
from ..runtime.enricher import AssetEnricher
from ..runtime.streamer import run_stream
from ..runtime.symbols import merge_symbols
from ..services.coin360_service import get_treemap_data
from ..services.fear_greed_service import get_feargreed

ENGINE = create_engine(os.getenv("DB_URL", "sqlite+aiosqlite:///./data.db"))
Session = async_sessionmaker(ENGINE, expire_on_commit=False)
REPO = TweetRepo(Session)
BROADCAST = Broadcaster()


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
    # start background stream: persist THEN broadcast
    task = asyncio.create_task(
        run_stream(REPO, BROADCAST)
    )  # ← we’ll update run_stream below
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


@app.post("/api/debug/tweet")
async def debug_tweet(body: DebugTweet):
    tickers, hashtags = merge_symbols(body.text, body.tickers, body.hashtags)
    symbols = tickers + hashtags
    assets = []
    if symbols:
        enricher = AssetEnricher()
        assets = await enricher.classify(symbols)
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
    }
    await REPO.upsert_many([tweet])
    await BROADCAST.publish(tweet)
    return tweet
