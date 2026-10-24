"""Analyst activity for one symbol: rating changes and estimate revisions.

``/api/research/valuation`` already has the consensus (average rating and
price targets), which moves slowly and says little about *now*. This module
covers what changes the consensus: recent upgrades, downgrades and price
target moves by named firms, how the buy/hold/sell split shifted over three
months, and whether EPS estimates are being revised up or down.

Everything comes from Yahoo through yfinance (three quoteSummary modules),
cached per symbol for an hour like the valuation data.
"""

import asyncio
import logging
import math
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 3600
_CACHE: dict[tuple[str, int], tuple[float, dict | None]] = {}

#: Most recent rating actions returned in ``recent_actions``.
MAX_ACTIONS = 12
DEFAULT_DAYS = 90

#: yfinance ``Action`` codes for a rating change.
_ACTION_NAMES = {
    "up": "upgrade",
    "down": "downgrade",
    "init": "initiated",
    "main": "maintained",
    "reit": "reiterated",
}
#: EPS-trend columns in the order they go back in time.
_TREND_COLUMNS = {
    "current": "current",
    "7daysAgo": "7d_ago",
    "30daysAgo": "30d_ago",
    "60daysAgo": "60d_ago",
    "90daysAgo": "90d_ago",
}
_REVISION_COLUMNS = {
    "upLast7days": "up_7d",
    "downLast7Days": "down_7d",
    "downLast7days": "down_7d",
    "upLast30days": "up_30d",
    "downLast30days": "down_30d",
}
_RATING_COLUMNS = ("strongBuy", "buy", "hold", "sell", "strongSell")
#: A 30-day EPS revision smaller than this (percent) reads as flat.
_FLAT_REVISION_PCT = 0.5


def _reset_cache_for_tests() -> None:
    _CACHE.clear()


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _records(frame: Any) -> list[dict]:
    """A DataFrame's rows as dicts, with its index under ``"index"``."""
    if frame is None or getattr(frame, "empty", True):
        return []
    return [{"index": index, **row} for index, row in frame.to_dict("index").items()]


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    to_pydatetime = getattr(value, "to_pydatetime", None)
    if callable(to_pydatetime):
        return to_pydatetime().date()
    return None


def summarize_actions(rows: list[dict], today: date, days: int) -> dict:
    """Rating changes and price-target moves inside the last ``days`` days.

    :param rows: ``upgrades_downgrades`` records (``index`` = grade date).
    """
    since = today - timedelta(days=days)
    actions = []
    for row in rows:
        day = _as_date(row.get("index") or row.get("GradeDate"))
        if day is None or day < since:
            continue
        current = _number(row.get("currentPriceTarget"))
        prior = _number(row.get("priorPriceTarget"))
        target_change = (
            round((current / prior - 1) * 100, 2) if current and prior else None
        )
        actions.append(
            {
                "date": day.isoformat(),
                "firm": row.get("Firm"),
                "action": _ACTION_NAMES.get(
                    str(row.get("Action") or "").lower(), row.get("Action")
                ),
                "from_grade": row.get("FromGrade") or None,
                "to_grade": row.get("ToGrade") or None,
                "price_target": current,
                "prior_price_target": prior,
                "target_change_percent": target_change,
            }
        )
    actions.sort(key=lambda a: a["date"], reverse=True)

    def count(name: str) -> int:
        return sum(1 for a in actions if a["action"] == name)

    target_raises = sum(1 for a in actions if (a["target_change_percent"] or 0) > 0)
    target_cuts = sum(1 for a in actions if (a["target_change_percent"] or 0) < 0)
    return {
        "days": days,
        "upgrades": count("upgrade"),
        "downgrades": count("downgrade"),
        "initiations": count("initiated"),
        "target_raises": target_raises,
        "target_cuts": target_cuts,
        "recent_actions": actions[:MAX_ACTIONS],
    }


def summarize_recommendations(rows: list[dict]) -> dict | None:
    """Buy/hold/sell counts now against three months ago.

    :param rows: ``recommendations`` records, one per ``period``
        (``0m`` = this month, ``-3m`` = three months ago).
    """
    by_period = {}
    for row in rows:
        period = row.get("period") or row.get("index")
        counts = {name: int(_number(row.get(name)) or 0) for name in _RATING_COLUMNS}
        if isinstance(period, str):
            by_period[period] = counts

    def buy_share(counts: dict | None) -> float | None:
        if not counts:
            return None
        total = sum(counts.values())
        if not total:
            return None
        return round((counts["strongBuy"] + counts["buy"]) / total * 100, 1)

    now = by_period.get("0m")
    if now is None:
        return None
    then = by_period.get("-3m") or by_period.get("-2m") or by_period.get("-1m")
    now_share, then_share = buy_share(now), buy_share(then)
    return {
        "now": now,
        "three_months_ago": then,
        "buy_percent": now_share,
        "buy_percent_change_3m": (
            round(now_share - then_share, 1)
            if now_share is not None and then_share is not None
            else None
        ),
    }


def summarize_estimates(trend_rows: list[dict], revision_rows: list[dict]) -> dict:
    """Consensus EPS per period, how it moved over 7/30/90 days, and how many
    analysts revised it up or down.

    ``direction`` reads the current fiscal year's 30-day change (falling back
    to next quarter's): ``rising``, ``falling`` or ``flat``.
    """
    revisions = {}
    for row in revision_rows:
        counts = {
            out: int(_number(row.get(col)) or 0)
            for col, out in _REVISION_COLUMNS.items()
            if col in row
        }
        revisions[str(row.get("index"))] = counts

    periods = {}
    for row in trend_rows:
        period = str(row.get("index"))
        values = {out: _number(row.get(col)) for col, out in _TREND_COLUMNS.items()}
        current = values["current"]
        entry: dict[str, Any] = {"eps_estimate": current}
        for label in ("7d_ago", "30d_ago", "90d_ago"):
            then = values[label]
            entry[f"change_{label.removesuffix('_ago')}_percent"] = (
                round((current / then - 1) * 100, 2)
                if current is not None and then
                else None
            )
        entry.update(revisions.get(period, {}))
        periods[period] = entry

    direction = None
    for period in ("0y", "+1q", "0q"):
        change = (periods.get(period) or {}).get("change_30d_percent")
        if change is not None:
            if change > _FLAT_REVISION_PCT:
                direction = "rising"
            elif change < -_FLAT_REVISION_PCT:
                direction = "falling"
            else:
                direction = "flat"
            break

    return {"direction": direction, "periods": periods}


def _fetch_sync(symbol: str) -> dict:
    """Blocking yfinance calls; always run via asyncio.to_thread."""
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    frames = {}
    for name in ("upgrades_downgrades", "recommendations", "eps_trend"):
        try:
            frames[name] = _records(getattr(ticker, name))
        except Exception as exc:
            logger.info("[analysts] %s %s failed: %r", symbol, name, exc)
            frames[name] = []
    # eps_revisions reuses the earningsTrend module eps_trend just fetched.
    try:
        frames["eps_revisions"] = _records(ticker.eps_revisions)
    except Exception as exc:
        logger.info("[analysts] %s eps_revisions failed: %r", symbol, exc)
        frames["eps_revisions"] = []
    return frames


async def get_analyst_activity(symbol: str, days: int = DEFAULT_DAYS) -> dict | None:
    """Recent rating changes, rating mix shift and EPS estimate revisions.

    :param symbol: Ticker symbol.
    :param days: Window for ``rating_changes``.
    :return: ``{symbol, rating_changes, recommendations, estimates}``, or
        ``None`` when Yahoo has none of them (funds, crypto, or Yahoo down).
    """
    normalized = (symbol or "").strip().upper()
    if not normalized:
        return None
    days = max(1, min(int(days), 365))

    key = (normalized, days)
    cached = _CACHE.get(key)
    if cached and time.time() - cached[0] <= _CACHE_TTL_SECONDS:
        return cached[1]

    try:
        frames = await asyncio.to_thread(_fetch_sync, normalized)
    except Exception as exc:
        logger.warning("[analysts] yfinance fetch failed for %s: %r", normalized, exc)
        return None

    if not any(frames.values()):
        # Not cached: an empty answer is as likely a Yahoo hiccup as a fund.
        return None

    payload = {
        "symbol": normalized,
        "rating_changes": summarize_actions(
            frames["upgrades_downgrades"], datetime.now(timezone.utc).date(), days
        ),
        "recommendations": summarize_recommendations(frames["recommendations"]),
        "estimates": summarize_estimates(frames["eps_trend"], frames["eps_revisions"]),
    }
    _CACHE[key] = (time.time(), payload)
    return payload
