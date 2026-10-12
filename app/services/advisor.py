"""Claude market check: decision-journal rules, pricing and the scorecard.

Claude logs each suggestion it makes during a market check (through the MCP
server's ``log_call`` tool). The call is priced when it is logged, re-priced
at each horizon by ``app/runtime/advisor_evaluator.py``, and graded the same
way trader calls are (``trader_scoring.grade_call``), so after a few weeks the
owner can see whether the suggestions are worth following.
"""

import re
from typing import Iterable

from .trader_scoring import _direction, grade_call

#: What a call can recommend. ``watch`` is a note ("keep an eye on X") and is
#: never graded; the others are graded in the direction they imply.
ACTIONS: tuple[str, ...] = ("buy", "add", "trim", "sell", "watch")
DIRECTION = {"buy": "bullish", "add": "bullish", "trim": "bearish", "sell": "bearish"}
GRADED_ACTIONS = tuple(DIRECTION)
CONVICTIONS: tuple[str, ...] = ("low", "medium", "high")
HORIZONS: tuple[int, ...] = (7, 30)

MAX_WATCHLIST = 50
MAX_FOLLOWED_TRADERS = 50
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-=^]{0,19}$")
# X handles: 1-15 letters, digits or underscores.
_SCREEN_NAME = re.compile(r"^[a-z0-9_]{1,15}$")


def normalize_symbol(symbol: str) -> str | None:
    """``$nvda`` -> ``NVDA``; None for anything that isn't a ticker."""
    cleaned = str(symbol or "").strip().upper().lstrip("$")
    return cleaned if _SYMBOL.match(cleaned) else None


def normalize_watchlist(symbols: list[str]) -> list[str]:
    """Deduplicated, upper-cased, order-preserving, invalid entries dropped."""
    seen: list[str] = []
    for raw in symbols:
        symbol = normalize_symbol(raw)
        if symbol and symbol not in seen:
            seen.append(symbol)
    return seen[:MAX_WATCHLIST]


def normalize_screen_names(names: list[str]) -> list[str]:
    """``@ShardiB2`` -> ``shardib2``; deduplicated, order-preserving, invalid
    handles dropped."""
    seen: list[str] = []
    for raw in names:
        name = str(raw or "").strip().lstrip("@").lower()
        if _SCREEN_NAME.match(name) and name not in seen:
            seen.append(name)
    return seen[:MAX_FOLLOWED_TRADERS]


def group_ticker_posts(
    tweets: list[dict],
    held: set[str],
    followed: Iterable[str] = (),
    max_posts: int = 3,
    max_traders: int = 10,
) -> list[dict]:
    """Turn tweets into one buy-idea lead per ticker.

    Each lead says how often the ticker came up, who posted about it (and
    which of them the owner follows), how many posts were bullish or bearish,
    the price when it was first seen, and a few posts with links: the
    followed traders' first, then the most liked. ``held`` symbols are flagged
    rather than dropped, since chatter about a holding is still worth knowing.
    Leads a followed trader posted about come first, then the most mentioned.
    """
    followed = {name.lower() for name in followed}
    leads: dict[str, dict] = {}
    candidates: dict[str, list[tuple[bool, int, dict]]] = {}
    for tweet in tweets:
        author = str(tweet.get("user_screen_name") or "")
        is_followed = author.lower() in followed
        per_ticker = tweet.get("ticker_sentiment") or {}
        tweet_score = tweet.get("sentiment_score")
        for raw in tweet.get("tickers") or []:
            symbol = normalize_symbol(raw)
            if symbol is None:
                continue
            score = per_ticker.get(symbol, per_ticker.get(raw, tweet_score))
            lead = leads.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "held": symbol in held,
                    "mentions": 0,
                    "followed_traders": [],
                    "traders": [],
                    "trader_count": 0,
                    "bullish": 0,
                    "bearish": 0,
                    "price_at_post": None,
                    "asset_kind": None,
                    "posts": [],
                },
            )
            lead["mentions"] += 1
            if author and author not in lead["traders"]:
                lead["traders"].append(author)
                if is_followed:
                    lead["followed_traders"].append(author)
            direction = _direction(score)
            if direction:
                lead[direction] += 1
            if lead["price_at_post"] is None:
                price, kind = price_from_assets(tweet.get("assets") or [], symbol)
                lead["price_at_post"], lead["asset_kind"] = price, kind
            candidates.setdefault(symbol, []).append(
                (
                    is_followed,
                    tweet.get("likes") or 0,
                    {
                        "trader": author,
                        "followed": is_followed,
                        "posted_at": tweet.get("created_at"),
                        "text": tweet.get("text"),
                        "url": tweet.get("url"),
                        "likes": tweet.get("likes"),
                        "sentiment": score,
                    },
                )
            )

    for symbol, lead in leads.items():
        # Stable sort keeps newest-first order among equals.
        picked = sorted(candidates[symbol], key=lambda c: (not c[0], -c[1]))
        lead["posts"] = [post for _, _, post in picked[:max_posts]]
        lead["trader_count"] = len(lead["traders"])
        lead["traders"] = lead["traders"][:max_traders]
    return sorted(
        leads.values(),
        key=lambda lead: (-len(lead["followed_traders"]), -lead["mentions"]),
    )


def price_from_assets(assets: list[dict], symbol: str) -> tuple[float | None, str]:
    """The price and asset kind for ``symbol`` out of an enricher result."""
    for asset in assets:
        if str(asset.get("symbol") or "").upper() != symbol:
            continue
        price = (asset.get("financials") or {}).get("price")
        kind = str(asset.get("kind") or "").upper() or None
        if isinstance(price, (int, float)) and price > 0:
            return float(price), kind
        return None, kind
    return None, None


def grade(action: str, price_at_call: float, price_now: float) -> dict:
    return grade_call(DIRECTION[action], price_at_call, price_now)


def _bucket(rows: list[dict]) -> dict:
    scored = [r for r in rows if not r.get("excluded")]
    if not scored:
        return {"graded": 0, "hit_rate": None, "avg_return_pct": None}
    signed = [
        r["return_pct"] if DIRECTION[r["action"]] == "bullish" else -r["return_pct"]
        for r in scored
    ]
    return {
        "graded": len(scored),
        "hit_rate": sum(1 for r in scored if r["correct"]) / len(scored),
        # What following the calls would have made, on average: a sell that
        # was followed by a 5% drop counts as +5%.
        "avg_return_pct": sum(signed) / len(signed),
    }


def build_scorecard(graded: list[dict], total_calls: int) -> dict:
    """Hit rate and average followed-return per horizon, and per action."""
    horizons = {}
    for horizon in HORIZONS:
        rows = [r for r in graded if r["horizon_days"] == horizon]
        horizons[str(horizon)] = {
            **_bucket(rows),
            "by_action": {
                action: _bucket([r for r in rows if r["action"] == action])
                for action in GRADED_ACTIONS
                if any(r["action"] == action for r in rows)
            },
        }
    return {"total_calls": total_calls, "horizons": horizons}
