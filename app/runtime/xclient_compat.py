from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import replace
from typing import Any

import xclient

logger = logging.getLogger(__name__)

_PATCH_APPLIED = False

# Every version id of an edited post, keyed by each parsed tweet id (issue #202).
# xtimeline's ``Tweet`` has no field for X's ``edit_control`` (and is slotted,
# so one can't be attached), so the parser patch records it here instead.
_EDIT_CHAINS: OrderedDict[int, tuple[int, ...]] = OrderedDict()
_EDIT_CHAINS_CAP = 5000


def _parse_edit_chain(tw: dict) -> tuple[int, ...]:
    """Read the ids of every version of a post from its ``edit_control``.

    X gives each edit a new id. The original carries ``edit_tweet_ids``
    directly; an edited version nests them under ``edit_control_initial``.
    """
    edit_control = tw.get("edit_control") if isinstance(tw, dict) else None
    if not isinstance(edit_control, dict):
        return ()

    initial = edit_control.get("edit_control_initial")
    source = initial if isinstance(initial, dict) else edit_control
    raw_ids = list(source.get("edit_tweet_ids") or [])
    if edit_control.get("initial_tweet_id") is not None:
        raw_ids.append(edit_control["initial_tweet_id"])

    ids: set[int] = set()
    for raw in raw_ids:
        try:
            ids.add(int(raw))
        except (TypeError, ValueError):
            continue
    return tuple(sorted(ids))


def _record_edit_chain(tweet_id: int, chain: tuple[int, ...]) -> None:
    if len(chain) < 2:
        return
    _EDIT_CHAINS[tweet_id] = chain
    _EDIT_CHAINS.move_to_end(tweet_id)
    while len(_EDIT_CHAINS) > _EDIT_CHAINS_CAP:
        _EDIT_CHAINS.popitem(last=False)


def edit_chain(tweet_id: int) -> tuple[int, ...]:
    """Ids of every version of an edited post, oldest first; empty if unedited."""
    return _EDIT_CHAINS.get(tweet_id, ())


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

    The patch also records each post's edit history for ``edit_chain``.

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
        if parsed is not None:
            _record_edit_chain(parsed.id, _parse_edit_chain(tw))
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
