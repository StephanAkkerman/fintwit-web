from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

import xclient

logger = logging.getLogger(__name__)

_PATCH_APPLIED = False


def _extract_nested_node(node: dict[str, Any]) -> dict[str, Any] | None:
    if "result" in node:
        result = node.get("result")
        if not isinstance(result, dict):
            return None

        if "tweet" in result:
            return xclient.normalize_tweet_result(node)
        return result

    normalized = xclient.normalize_tweet_result({"result": node})
    if isinstance(normalized, dict):
        return normalized
    if isinstance(node, dict):
        return node
    return None


def apply_xclient_retweet_patch() -> None:
    """Patch xclient parser so retweets carry original tweet metadata.

    xtimeline 0.1.4 stores retweet attribution in ``title`` but drops the nested
    original tweet object. This makes downstream UI attribution impossible.
    We patch ``_parse_single_tweet`` to attach the nested retweeted tweet under
    ``quoted_tweet`` only when missing.
    """

    global _PATCH_APPLIED
    if _PATCH_APPLIED:
        return

    client_cls = getattr(xclient, "XTimelineClient", None)
    if client_cls is None or not hasattr(client_cls, "_parse_single_tweet"):
        logger.warning(
            "[xclient-compat] skipping retweet parser patch; _parse_single_tweet is unavailable"
        )
        return

    original_parser = client_cls._parse_single_tweet

    def patched_parse_single_tweet(self: xclient.XTimelineClient, tw: dict):
        parsed = original_parser(self, tw)
        if parsed is None or parsed.quoted_tweet is not None:
            return parsed

        title = str(getattr(parsed, "title", "") or "")
        if "retweeted" not in title.lower():
            return parsed

        legacy = tw.get("legacy") if isinstance(tw, dict) else None
        if not isinstance(legacy, dict):
            return parsed

        retweeted_node = legacy.get("retweeted_status_result")
        if not isinstance(retweeted_node, dict):
            return parsed

        nested_node = _extract_nested_node(retweeted_node)
        if not isinstance(nested_node, dict):
            return parsed

        nested = self._parse_single_tweet(nested_node)
        if nested is None:
            return parsed

        return replace(parsed, quoted_tweet=nested)

    client_cls._parse_single_tweet = patched_parse_single_tweet
    _PATCH_APPLIED = True
    logger.info("[xclient-compat] retweet parser patch applied")
