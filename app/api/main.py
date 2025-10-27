# app/api/main.py
import asyncio
import json
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..runtime.broadcast import Broadcaster
from ..runtime.state import TweetStore
from ..runtime.streamer import run_stream

STORE = TweetStore(capacity=5000)
BROADCAST = Broadcaster()


def _check_api_key(expected: str | None, got: str | None):
    if expected:
        if not got or got != expected:
            raise HTTPException(status_code=401, detail="Unauthorized")


async def api_key_dep(request: Request):
    _check_api_key(request.app.state.API_KEY, request.headers.get("X-API-Key"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # put your API key in env later; empty means "no auth"
    app.state.API_KEY = ""  # e.g. os.getenv("API_KEY", "")
    task = asyncio.create_task(run_stream(STORE, BROADCAST))
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="X Stream Backend", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/api/posts")
async def list_posts(
    limit: int = Query(50, ge=1, le=200),
    _=Depends(api_key_dep),
):
    return await STORE.latest(limit=limit)


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
