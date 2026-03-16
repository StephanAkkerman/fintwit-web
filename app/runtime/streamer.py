import asyncio

import xclient

from ..infra.repos import TweetRepo
from .broadcast import Broadcaster
from .enricher import AssetEnricher


async def run_stream(repo: TweetRepo, bc: Broadcaster) -> None:
    backoff = 1.0
    enricher = AssetEnricher()

    while True:
        try:
            async with xclient.XTimelineClient("curl.txt") as xc:
                async for t in xc.stream(interval_s=5.0):

                    # Convert to dict for easier manipulation
                    t_dict = t.to_dict()

                    # Collect all symbols (tickers + hashtags) to classify
                    symbols = []
                    if t_dict.get("tickers"):
                        symbols.extend(t_dict["tickers"])
                    if t_dict.get("hashtags"):
                        symbols.extend(t_dict["hashtags"])

                    # Enrich the tweet with financial info if there are symbols
                    if symbols:
                        assets = await enricher.classify(symbols)
                        t_dict["assets"] = assets
                    else:
                        t_dict["assets"] = []

                    # 1) persist (idempotent)
                    await repo.upsert_many([t_dict])
                    # 2) broadcast after successful commit
                    await bc.publish(t_dict)

            backoff = 1.0
        except Exception as e:
            print(f"[stream] error: {e!r}; retrying in {backoff:.1f}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
