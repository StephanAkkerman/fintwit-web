# app/runtime/streamer.py
import asyncio

import xclient

from .broadcast import Broadcaster
from .state import TweetStore


async def run_stream(store: TweetStore, bc: Broadcaster) -> None:
    """Pull from X, push into memory + broadcast."""
    backoff = 1.0
    while True:
        try:
            async with xclient.XTimelineClient(
                "curl.txt", persist_last_id_path="state/last_id.txt"
            ) as xc:
                async for t in xc.stream(interval_s=5.0):
                    # t is already a Tweet
                    await store.append(t)
                    await bc.publish(t.to_dict())
            backoff = 1.0
        except Exception as e:
            # swap for structured logging if you like
            print(f"[stream] error: {e!r} -> retry in {backoff:.1f}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
