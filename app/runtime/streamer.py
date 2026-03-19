# app/runtime/streamer.py (swap TweetStore for TweetRepo)
import asyncio

import xclient

from ..infra.repos import TweetRepo
from .broadcast import Broadcaster
from .enricher import AssetEnricher
from ..ml.chart import chart_classifier


async def run_stream(repo: TweetRepo, bc: Broadcaster, enricher: AssetEnricher) -> None:
    backoff = 1.0
    while True:
        try:
            async with xclient.XTimelineClient("curl.txt") as xc:
                async for t in xc.stream(interval_s=5.0):
                    t_dict = t.to_dict()

                    if "assets" not in t_dict:
                        t_dict["assets"] = await enricher.classify(t_dict.get("tickers", []))

                    t_dict["is_chart"] = False

                    if t_dict.get("media") and t_dict.get("media_types"):
                        for media_url, media_type in zip(t_dict["media"], t_dict["media_types"]):
                            if media_type == "photo":
                                classification = await chart_classifier.classify_image_async(media_url)
                                if classification == "chart":
                                    t_dict["is_chart"] = True
                                    break

                    # 1) persist (idempotent)
                    await repo.upsert_many([t_dict])
                    # 2) broadcast after successful commit
                    await bc.publish(t_dict)
            backoff = 1.0
        except Exception as e:
            print(f"[stream] error: {e!r}; retrying in {backoff:.1f}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
