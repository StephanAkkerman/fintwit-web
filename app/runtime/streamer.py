import asyncio
import os
from datetime import datetime
from pathlib import Path

import xclient

from ..infra.repos import TweetRepo
from .broadcast import Broadcaster
from .enricher import AssetEnricher
from .symbols import merge_symbols

ENGAGEMENT_FIELDS = ("replies", "likes", "views", "retweets")


def _extract_engagement_fields(tweet_payload: dict) -> dict:
    updates: dict = {}
    for key in ENGAGEMENT_FIELDS:
        value = tweet_payload.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            updates[key] = int(value)
    return updates


async def run_stream(repo: TweetRepo, bc: Broadcaster) -> None:
    backoff = 1.0
    enricher = AssetEnricher()
    last_id_path = os.getenv("XTIMELINE_LAST_ID_PATH", "state/last_id.txt")
    Path(last_id_path).parent.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            async with xclient.XTimelineClient(
                "curl.txt",
                persist_last_id_path=last_id_path,
            ) as xc:
                async for t in xc.stream(interval_s=5.0, mode="with_updates"):

                    # Convert to dict for easier manipulation
                    t_dict = t.to_dict()

                    if getattr(t, "is_update", False):
                        tweet_id = t_dict.get("id")
                        if tweet_id is None:
                            continue

                        updates = _extract_engagement_fields(t_dict)
                        if not updates:
                            continue

                        updated_tweet = await repo.update_fields(int(tweet_id), updates)
                        if updated_tweet is not None:
                            await bc.publish(updated_tweet)
                        continue

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
