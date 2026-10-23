"""Claude market check: decision-journal rules, pricing and the scorecard.

Claude logs each suggestion it makes during a market check (through the MCP
server's ``log_call`` tool). The call is priced when it is logged, re-priced
at each horizon by ``app/runtime/advisor_evaluator.py``, and graded the same
way trader calls are (``trader_scoring.grade_call``), so after a few weeks the
owner can see whether the suggestions are worth following.

Alongside the owner's own advice, the check paper-trades a few rule-based
strategies (``PAPER_STRATEGIES``). Their calls carry a ``strategy`` tag, never
reach the owner's journal, and each strategy keeps a paper portfolio: a
``buy`` opens an equal-sized position, a ``sell`` closes it, and a strategy
with a holding period closes it at the graded price when that runs out. The
/advisor page compares them, so a strategy earns real money only after it has
shown it works.
"""

import re
from datetime import datetime, timezone
from typing import Iterable

from .trader_scoring import _direction, grade_call

#: What a call can recommend. ``watch`` is a note ("keep an eye on X") and is
#: never graded; the others are graded in the direction they imply.
ACTIONS: tuple[str, ...] = ("buy", "add", "trim", "sell", "watch")
DIRECTION = {"buy": "bullish", "add": "bullish", "trim": "bearish", "sell": "bearish"}
GRADED_ACTIONS = tuple(DIRECTION)
CONVICTIONS: tuple[str, ...] = ("low", "medium", "high")
HORIZONS: tuple[int, ...] = (7, 30)

#: The tag of the owner's own advice; every other tag is a paper strategy.
ADVISOR = "advisor"

#: Rule-based strategies the market check paper-trades. ``entry`` and ``exit``
#: are what the check follows (and the /advisor page shows); ``max_hold_days``
#: closes a position at that horizon's graded price when no sell came first,
#: so it must be one of ``HORIZONS`` (None: held until a sell).
PAPER_STRATEGIES: dict[str, dict] = {
    "insider_cluster": {
        "label": "Insider cluster buys",
        "entry": "Three or more insiders bought on the open market (SEC Form 4, "
        "no option exercises) within about two weeks, and the stock is above "
        "its 200-day average.",
        "exit": "Sell when it closes below the 50-day average or falls 15% from "
        "entry; otherwise held for 30 days.",
        "max_hold_days": 30,
    },
    "earnings_drift": {
        "label": "Post-earnings drift",
        "entry": "Beat the EPS consensus (and revenue, where it is known), "
        "gapped up, and held the gain for two trading days after the report.",
        "exit": "Sell when it gives back the whole earnings gap; otherwise held "
        "for 30 days.",
        "max_hold_days": 30,
    },
    "extreme_fear": {
        "label": "Buying extreme fear",
        "entry": "Stock fear & greed below 20 with broad weakness (most stocks "
        "below their 50-day average): buy SPY, or a quality name that is down "
        "with the market rather than on its own news.",
        "exit": "Sell when fear & greed is back above 60.",
        "max_hold_days": None,
    },
    "call_flow": {
        "label": "Big call buying",
        "entry": "Unusually large call buying (Signa options flow: sweeps or "
        "blocks at the ask, well above normal volume) and the stock confirms it "
        "by closing up on above-average volume.",
        "exit": "Sell when it closes below the price it had when the flow came "
        "in; otherwise held for 7 days.",
        "max_hold_days": 7,
    },
}
#: What a paper call can be: a position is opened and closed, never sized.
PAPER_ACTIONS: tuple[str, ...] = ("buy", "sell", "watch")

MAX_WATCHLIST = 50
MAX_FOLLOWED_TRADERS = 50
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-=^]{0,19}$")
# X handles: 1-15 letters, digits or underscores.
_SCREEN_NAME = re.compile(r"^[a-z0-9_]{1,15}$")


def normalize_symbol(symbol: str) -> str | None:
    """``$nvda`` -> ``NVDA``; None for anything that isn't a ticker."""
    cleaned = str(symbol or "").strip().upper().lstrip("$")
    return cleaned if _SYMBOL.match(cleaned) else None


def normalize_strategy(strategy: str | None) -> str | None:
    """``None``/``"advisor"`` -> ``None`` (the owner's advice), a paper
    strategy's key -> that key, anything else -> ``ValueError``."""
    key = str(strategy or "").strip().lower()
    if key in ("", ADVISOR):
        return None
    if key not in PAPER_STRATEGIES:
        raise ValueError(
            f"strategy must be {ADVISOR!r} or one of {tuple(PAPER_STRATEGIES)}"
        )
    return key


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
    """Hit rate and average followed-return per horizon, and per action, of
    the owner's advice; the paper strategies' entries are scored apart, under
    ``strategies``, so they never flatter or drag the real record."""
    paper = [r for r in graded if r.get("strategy")]
    graded = [r for r in graded if not r.get("strategy")]
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
    strategies = {
        key: {
            str(horizon): _bucket(
                [
                    r
                    for r in paper
                    if r["strategy"] == key and r["horizon_days"] == horizon
                ]
            )
            for horizon in HORIZONS
        }
        for key in PAPER_STRATEGIES
    }
    return {"total_calls": total_calls, "horizons": horizons, "strategies": strategies}


def build_paper_portfolios(
    calls: list[dict], prices: dict[str, float], today=None
) -> list[dict]:
    """Every paper strategy's positions and how they did.

    ``calls`` are the strategy-tagged calls, oldest first, each with its graded
    ``results``; ``prices`` the current price of the open symbols. A ``buy``
    opens a position (one per symbol at a time), the next ``sell`` of that
    symbol closes it at the sell's price, and a position held past its
    strategy's ``max_hold_days`` closes at that horizon's graded price. Open
    positions are marked at ``prices`` and count towards the return, so a
    strategy sitting on losers isn't flattered by its few closed winners.
    """
    now = today or datetime.now(timezone.utc)
    by_strategy: dict[str, list[dict]] = {key: [] for key in PAPER_STRATEGIES}
    open_by: dict[tuple[str, str], dict] = {}
    for call in calls:
        key = call.get("strategy")
        if key not in by_strategy:
            continue
        slot = (key, call["symbol"])
        if call["action"] == "buy" and slot not in open_by:
            if not call.get("price_at_call"):
                continue
            position = {
                "symbol": call["symbol"],
                "entry_call_id": call["id"],
                "entry_price": call["price_at_call"],
                "entered_at": call["called_at"],
                "exit_price": None,
                "exited_at": None,
                "exit_reason": None,
                "results": call.get("results") or {},
            }
            open_by[slot] = position
            by_strategy[key].append(position)
        elif call["action"] == "sell" and slot in open_by:
            position = open_by.pop(slot)
            if call.get("price_at_call"):
                position["exit_price"] = call["price_at_call"]
                position["exited_at"] = call["called_at"]
                position["exit_reason"] = "sell"
            else:
                open_by[slot] = position

    portfolios = []
    for key, spec in PAPER_STRATEGIES.items():
        positions = by_strategy[key]
        hold = spec["max_hold_days"]
        for position in positions:
            results = position.pop("results")
            result = results.get(str(hold)) if hold else None
            if position["exit_price"] is None and result and not result.get("excluded"):
                position["exit_price"] = result["price_at_horizon"]
                position["exited_at"] = result.get("evaluated_at")
                position["exit_reason"] = f"held {hold} days"
            closed = position["exit_price"] is not None
            price = position["exit_price"] if closed else prices.get(position["symbol"])
            position["status"] = "closed" if closed else "open"
            position["price_now"] = None if closed else price
            position["return_pct"] = (
                (price - position["entry_price"]) / position["entry_price"] * 100.0
                if price
                else None
            )
            entered = _parse_time(position["entered_at"])
            ended = _parse_time(position["exited_at"]) if closed else now
            position["days_held"] = (
                max(0, (ended - entered).days) if entered and ended else None
            )
        priced = [p for p in positions if p["return_pct"] is not None]
        closed = [p for p in priced if p["status"] == "closed"]
        portfolios.append(
            {
                "strategy": key,
                **spec,
                "positions": sorted(
                    positions, key=lambda p: p["entered_at"] or "", reverse=True
                ),
                "open": sum(1 for p in positions if p["status"] == "open"),
                "closed": len(closed),
                # Of the closed positions, the share that made money.
                "win_rate": (
                    sum(1 for p in closed if p["return_pct"] > 0) / len(closed)
                    if closed
                    else None
                ),
                # Equal money in every position: the portfolio's return.
                "avg_return_pct": (
                    sum(p["return_pct"] for p in priced) / len(priced)
                    if priced
                    else None
                ),
            }
        )
    return portfolios


def _parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
