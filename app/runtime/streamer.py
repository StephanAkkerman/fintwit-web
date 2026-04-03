import asyncio
from datetime import datetime

import xclient

from ..infra.repos import TweetRepo
from .broadcast import Broadcaster
from .enricher import AssetEnricher
from .symbols import merge_symbols


async def run_stream(repo: TweetRepo, bc: Broadcaster) -> None:
    backoff = 1.0
    enricher = AssetEnricher()

    while True:
        try:
            async with xclient.XTimelineClient("curl.txt") as xc:
                async for t in xc.stream(interval_s=5.0):

                    # Convert to dict for easier manipulation
                    t_dict = t.to_dict()

                    # SQLAlchemy DateTime requires a datetime object, not a string
                    if isinstance(t_dict.get("created_at"), str):
                        t_dict["created_at"] = datetime.fromisoformat(
                            t_dict["created_at"]
                        )

                    # Ensure financial symbols are still detected when source payloads
                    # don't explicitly include ticker/hashtag arrays.
                    tickers, hashtags = merge_symbols(
                        t_dict.get("text"),
                        t_dict.get("tickers"),
                        t_dict.get("hashtags"),
                    )
                    t_dict["tickers"] = tickers
                    t_dict["hashtags"] = hashtags
                    symbols = [*tickers, *hashtags]

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
