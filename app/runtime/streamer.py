import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

import xclient

from ..infra.repos import TweetRepo
from ..ml.chart import is_chart
from ..ml.sentiment import FinTwitSentiment
from .broadcast import Broadcaster
from .enricher import AssetEnricher
from .options_intent import classify_options_intent
from .symbols import merge_symbols
from .xclient_compat import apply_xclient_retweet_patch

ENGAGEMENT_FIELDS = ("replies", "likes", "views", "retweets")
logger = logging.getLogger(__name__)


def _extract_engagement_fields(tweet_payload: dict) -> dict:
    updates: dict = {}
    for key in ENGAGEMENT_FIELDS:
        value = tweet_payload.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            updates[key] = int(value)
    return updates


def _extract_photo_urls(tweet_payload: dict) -> list[str]:
    media = tweet_payload.get("media") or []
    media_types = tweet_payload.get("media_types") or []

    urls: list[str] = []
    for idx, item in enumerate(media):
        item_type = media_types[idx] if idx < len(media_types) else None

        url: str | None = None
        if isinstance(item, dict):
            url = item.get("url")
            item_type = item_type or item.get("type")
        elif isinstance(item, str):
            url = item

        if item_type == "photo" and isinstance(url, str) and url:
            urls.append(url)

    return urls


async def run_stream(
    repo: TweetRepo,
    bc: Broadcaster,
    sentiment_model: FinTwitSentiment | None = None,
) -> None:
    apply_xclient_retweet_patch()
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
                    asset_symbols = [*tickers]

                    options_signal = classify_options_intent(t_dict.get("text"))
                    t_dict["is_options_tweet"] = options_signal["is_options_tweet"]
                    t_dict["options_context"] = (
                        options_signal["options_context"]
                        if options_signal["is_options_tweet"]
                        else None
                    )

                    # Enrich assets from cashtags/tickers only. Hashtags are kept
                    # for display/filter metadata but are too noisy for asset cards.
                    if asset_symbols:
                        assets = await enricher.classify(asset_symbols)
                        t_dict["assets"] = assets
                    else:
                        t_dict["assets"] = []

                    # Run chart detection on all photo tweets so chart filters
                    # don't fallback to treating every image as a chart.
                    media_urls = _extract_photo_urls(t_dict)
                    if media_urls:
                        results = await asyncio.gather(
                            *[is_chart(url) for url in media_urls],
                            return_exceptions=True,
                        )
                        t_dict["has_chart"] = any(r is True for r in results)
                    else:
                        t_dict["has_chart"] = False

                    main_sentiment = None
                    quoted_sentiment = None
                    if sentiment_model is not None and symbols:
                        try:
                            sentiment_parts = await sentiment_model.classify_parts(
                                t_dict.get("text") or ""
                            )
                            main_sentiment = sentiment_parts.get("main")
                            quoted_sentiment = sentiment_parts.get("quoted")
                        except Exception as exc:
                            logger.warning(
                                "[stream] sentiment classification failed: %r", exc
                            )

                    t_dict["sentiment_label"] = (
                        main_sentiment["label"] if main_sentiment else None
                    )
                    t_dict["sentiment_emoji"] = (
                        main_sentiment["emoji"] if main_sentiment else None
                    )
                    t_dict["sentiment_score"] = (
                        main_sentiment["score"] if main_sentiment else None
                    )
                    t_dict["quoted_sentiment_label"] = (
                        quoted_sentiment["label"] if quoted_sentiment else None
                    )
                    t_dict["quoted_sentiment_emoji"] = (
                        quoted_sentiment["emoji"] if quoted_sentiment else None
                    )
                    t_dict["quoted_sentiment_score"] = (
                        quoted_sentiment["score"] if quoted_sentiment else None
                    )

                    # 1) persist (idempotent)
                    await repo.upsert_many([t_dict])
                    # 2) broadcast after successful commit
                    await bc.publish(t_dict)

            backoff = 1.0
        except Exception as e:
            print(f"[stream] error: {e!r}; retrying in {backoff:.1f}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
