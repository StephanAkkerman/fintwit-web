"""Options flow and dark pool prints from Signa, summarised per symbol.

Signa relays Unusual Whales' flow and scores it. Two feeds are read:

- **curated flow**: trades Signa's agents scored for conviction, each with a
  direction (bullish/bearish/hedging) and a one-line rationale. Selling puts
  reads bullish here, so direction is Signa's take, not the option type.
- **raw flow**: every execution above $250k premium, with Unusual Whales'
  sentiment, which shows where the big money went (calls vs puts).

Both cover roughly the last trading day. One market-wide call per feed is
enough to rank symbols for buy ideas and to look up every holding, which
matters because the Signa key allows 1000 calls a day shared with the market
check itself; a single symbol is only fetched on its own for a deep dive.

Dark pool prints (off-exchange trades) are summarised by where they printed
against the quote: at or above the ask leans on buyers, at or below the bid
on sellers. Signa returns only the latest prints, so this is a snapshot of
the last minutes rather than a day's total.
"""

import asyncio
from collections import defaultdict
from typing import Any

from .signa import SignaClient

#: Flow is a day-long sample that Signa refreshes every few minutes.
_FLOW_CACHE_SECONDS = 300
_client = SignaClient(cache_ttl_seconds=_FLOW_CACHE_SECONDS)

CURATED_LIMIT = 100
RAW_LIMIT = 200
RAW_MIN_PREMIUM = 250_000
DARK_POOL_LIMIT = 50
#: Events and symbols listed in a summary.
TOP_EVENTS = 5
TOP_SYMBOLS = 10


def has_flow_access() -> bool:
    return bool(_client.api_key)


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _curated_event(item: dict) -> dict:
    flow = item.get("flow_events") or {}
    return {
        "symbol": _symbol(flow.get("symbol")),
        "direction": item.get("direction"),
        "conviction": item.get("conviction_score"),
        "option_type": flow.get("option_type"),
        "strike": flow.get("strike"),
        "expiry": flow.get("expiry"),
        "dte": flow.get("dte"),
        "premium": _num(flow.get("premium_size")),
        "sweep": bool(flow.get("is_sweep")),
        "block": bool(flow.get("is_block")),
        "confirms_signal": item.get("confirms_signal"),
        "rationale": item.get("rationale_short"),
        "at": flow.get("timestamp") or item.get("scored_at"),
    }


def _raw_event(item: dict) -> dict:
    return {
        "symbol": _symbol(item.get("symbol")),
        "option_type": item.get("option_type"),
        "sentiment": item.get("sentiment"),
        "strike": item.get("strike"),
        "expiry": item.get("expiry"),
        "dte": item.get("dte"),
        "premium": _num(item.get("premium_size")),
        "sweep": bool(item.get("is_sweep")),
        "block": bool(item.get("is_block")),
        "volume_oi_ratio": item.get("volume_oi_ratio"),
        "at": item.get("executed_at"),
    }


def summarize_flow(curated: list[dict], raw: list[dict]) -> dict:
    """One symbol's (or the market's) flow from normalised events.

    ``bias`` follows the premium-weighted direction of the curated (scored)
    trades, falling back to raw sentiment when nothing was scored.
    """
    premium: dict[str, float] = defaultdict(float)
    for event in curated:
        premium[str(event["direction"] or "").lower()] += event["premium"]
    raw_premium: dict[str, float] = defaultdict(float)
    for event in raw:
        raw_premium[f"{event['option_type']}_{event['sentiment']}".lower()] += event[
            "premium"
        ]
        raw_premium[str(event["option_type"] or "").lower()] += event["premium"]
        raw_premium[str(event["sentiment"] or "").lower() + "_all"] += event["premium"]

    if curated:
        bullish, bearish = premium["bullish"], premium["bearish"]
    else:
        bullish, bearish = raw_premium["bullish_all"], raw_premium["bearish_all"]
    bias = None
    if bullish or bearish:
        if bullish >= 2 * bearish:
            bias = "bullish"
        elif bearish >= 2 * bullish:
            bias = "bearish"
        else:
            bias = "mixed"

    convictions = [e["conviction"] for e in curated if e["conviction"] is not None]
    return {
        "bias": bias,
        "scored_trades": len(curated),
        "scored_bullish": sum(1 for e in curated if e["direction"] == "BULLISH"),
        "scored_bearish": sum(1 for e in curated if e["direction"] == "BEARISH"),
        "scored_bullish_premium": round(premium["bullish"]),
        "scored_bearish_premium": round(premium["bearish"]),
        "avg_conviction": (
            round(sum(convictions) / len(convictions)) if convictions else None
        ),
        "large_trades": len(raw),
        "call_premium": round(raw_premium["call"]),
        "put_premium": round(raw_premium["put"]),
        "bullish_call_premium": round(raw_premium["call_bullish"]),
        "bearish_put_premium": round(raw_premium["put_bearish"]),
        "top_scored": sorted(curated, key=lambda e: -e["premium"])[:TOP_EVENTS],
        "top_large": sorted(raw, key=lambda e: -e["premium"])[:TOP_EVENTS],
    }


def _events(payload: Any, key: str = "events") -> list[dict]:
    if not isinstance(payload, dict):
        return []
    items = payload.get(key)
    return [item for item in items if isinstance(item, dict)] if items else []


async def _fetch_flow(symbol: str | None) -> tuple[Any, Any]:
    curated_args: dict[str, Any] = {"limit": CURATED_LIMIT}
    raw_args: dict[str, Any] = {"limit": RAW_LIMIT, "min_premium": RAW_MIN_PREMIUM}
    if symbol:
        curated_args["symbol"] = raw_args["symbol"] = symbol
    return await asyncio.gather(
        _client.call_tool("get_curated_flow", curated_args),
        _client.call_tool("get_raw_flow", raw_args),
    )


async def get_options_flow(symbol: str | None = None) -> dict | None:
    """Options flow for one symbol, or market-wide with a per-symbol breakdown.

    :param symbol: Ticker, or ``None`` for the whole market.
    :return: ``None`` when no key is set or both feeds failed. Market-wide,
        the summary carries ``by_symbol`` (every symbol with flow) and
        ``top_bullish``/``top_bearish`` (symbols ranked by scored premium).
    """
    symbol = _symbol(symbol) or None
    curated_payload, raw_payload = await _fetch_flow(symbol)
    if curated_payload is None and raw_payload is None:
        return None

    curated = [_curated_event(item) for item in _events(curated_payload)]
    raw = [_raw_event(item) for item in _events(raw_payload)]
    if symbol:
        curated = [e for e in curated if e["symbol"] == symbol]
        raw = [e for e in raw if e["symbol"] == symbol]

    result: dict[str, Any] = {
        "symbol": symbol,
        "source": "Signa (Unusual Whales)",
        "curated_available": curated_payload is not None,
        "raw_available": raw_payload is not None,
        **summarize_flow(curated, raw),
    }
    if symbol:
        return result

    symbols = sorted({e["symbol"] for e in curated + raw if e["symbol"]})
    by_symbol = {
        sym: summarize_flow(
            [e for e in curated if e["symbol"] == sym],
            [e for e in raw if e["symbol"] == sym],
        )
        for sym in symbols
    }
    for summary in by_symbol.values():
        summary["top_scored"] = summary["top_scored"][:2]
        summary["top_large"] = summary["top_large"][:2]

    def ranked(field: str) -> list[dict]:
        rows = [
            {"symbol": sym, field: s[field], "bias": s["bias"]}
            for sym, s in by_symbol.items()
            if s[field] > 0
        ]
        return sorted(rows, key=lambda r: -r[field])[:TOP_SYMBOLS]

    result["top_bullish"] = ranked("scored_bullish_premium")
    result["top_bearish"] = ranked("scored_bearish_premium")
    result["top_call_buying"] = ranked("bullish_call_premium")
    result["by_symbol"] = by_symbol
    return result


def summarize_dark_pool(prints: list[dict]) -> dict:
    """Notional and buy/sell lean of a batch of dark pool prints."""
    live = [p for p in prints if not p.get("canceled")]
    notional = at_ask = at_bid = 0.0
    largest: list[dict] = []
    for p in live:
        price = _num(p.get("price"))
        value = _num(p.get("premium")) or price * _num(p.get("size"))
        notional += value
        bid, ask = _num(p.get("nbbo_bid")), _num(p.get("nbbo_ask"))
        if ask and price >= ask:
            at_ask += value
        elif bid and price <= bid:
            at_bid += value
        largest.append(
            {
                "price": price,
                "size": p.get("size"),
                "notional": round(value),
                "at": p.get("executed_at"),
            }
        )
    lean = None
    if at_ask or at_bid:
        if at_ask >= 1.5 * at_bid:
            lean = "buyers"
        elif at_bid >= 1.5 * at_ask:
            lean = "sellers"
        else:
            lean = "balanced"
    times = sorted(str(p.get("executed_at")) for p in live if p.get("executed_at"))
    return {
        "prints": len(live),
        "notional": round(notional),
        "at_or_above_ask_notional": round(at_ask),
        "at_or_below_bid_notional": round(at_bid),
        "lean": lean,
        "from": times[0] if times else None,
        "to": times[-1] if times else None,
        "largest": sorted(largest, key=lambda r: -r["notional"])[:TOP_EVENTS],
    }


async def get_dark_pool(symbol: str) -> dict | None:
    """The latest dark pool prints for one symbol, summarised."""
    symbol = _symbol(symbol)
    if not symbol:
        return None
    payload = await _client.call_tool(
        "get_dark_pool", {"ticker": symbol, "limit": DARK_POOL_LIMIT}
    )
    if payload is None:
        return None
    prints = [
        p for p in _events(payload, "prints") if _symbol(p.get("ticker")) == symbol
    ]
    return {
        "symbol": symbol,
        "source": "Signa (Unusual Whales)",
        **summarize_dark_pool(prints),
    }
