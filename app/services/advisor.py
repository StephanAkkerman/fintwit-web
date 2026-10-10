"""Claude market check: decision-journal rules, pricing and the scorecard.

Claude logs each suggestion it makes during a market check (through the MCP
server's ``log_call`` tool). The call is priced when it is logged, re-priced
at each horizon by ``app/runtime/advisor_evaluator.py``, and graded the same
way trader calls are (``trader_scoring.grade_call``), so after a few weeks the
owner can see whether the suggestions are worth following.
"""

import re

from .trader_scoring import grade_call

#: What a call can recommend. ``watch`` is a note ("keep an eye on X") and is
#: never graded; the others are graded in the direction they imply.
ACTIONS: tuple[str, ...] = ("buy", "add", "trim", "sell", "watch")
DIRECTION = {"buy": "bullish", "add": "bullish", "trim": "bearish", "sell": "bearish"}
GRADED_ACTIONS = tuple(DIRECTION)
CONVICTIONS: tuple[str, ...] = ("low", "medium", "high")
HORIZONS: tuple[int, ...] = (7, 30)

MAX_WATCHLIST = 50
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-=^]{0,19}$")


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
