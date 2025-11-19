# app/runtime/streamer.py (swap TweetStore for TweetRepo)
import asyncio

import xclient

from ..infra.repos import TweetRepo
from .broadcast import Broadcaster


async def run_stream(repo: TweetRepo, bc: Broadcaster) -> None:
    backoff = 1.0
    while True:
        try:
            async with xclient.XTimelineClient("curl.txt") as xc:
                async for t in xc.stream(interval_s=5.0):
                    # 1) persist (idempotent)
                    await repo.upsert_many([t])
                    # 2) broadcast after successful commit
                    await bc.publish(t.to_dict())
            backoff = 1.0
        except Exception as e:
            print(f"[stream] error: {e!r}; retrying in {backoff:.1f}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
