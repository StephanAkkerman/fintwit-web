"""Quote for one option contract a tweet names (issue #216).

Tweets write expiries loosely ("11/06", "11/06/2026", "NOV", "Nov 21"); this
resolves them against the expirations Yahoo lists for the underlying and looks
the contract up in that expiration's chain (the cached
:func:`app.services.options_chain_service.get_options_chain`).
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from .options_chain_service import get_options_chain

_MONTHS = {name.upper(): i for i, name in enumerate(calendar.month_abbr) if name}

_ISO_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_SLASH_RE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$")
_MONTH_RE = re.compile(
    r"^(?:(\d{1,2})\s*)?([A-Z]{3})[A-Z]*\.?(?:\s*(\d{1,2}))?(?:\s*,?\s*'?(\d{2,4}))?$"
)

#: How far a written date may sit from a listed expiration and still match it
#: (a holiday moves a Friday expiry to Thursday; posters round to the Friday).
_MATCH_WINDOW = timedelta(days=3)


def _third_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    first_friday = first + timedelta(days=(4 - first.weekday()) % 7)
    return first_friday + timedelta(weeks=2)


def _full_year(raw: str | None) -> int | None:
    if not raw:
        return None
    year = int(raw)
    return year + 2000 if year < 100 else year


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_expiry(expiry: str | None, as_of: date) -> date | None:
    """The date *expiry* most likely means for a tweet posted on *as_of*.

    A date without a year is the next one on or after the post (allowing a
    day of slack); a bare month is that month's standard monthly expiry, the
    third Friday.
    """
    text = re.sub(r"\s*EXP(?:IRY|IRATION)?\b", "", (expiry or "").strip().upper())
    text = text.strip()
    if not text:
        return None

    if match := _ISO_RE.match(text):
        return _safe_date(*(int(g) for g in match.groups()))

    if match := _SLASH_RE.match(text):
        month, day = int(match.group(1)), int(match.group(2))
        year = _full_year(match.group(3))
        if year is not None:
            return _safe_date(year, month, day)
        candidate = _safe_date(as_of.year, month, day)
        if candidate is not None and candidate < as_of - timedelta(days=1):
            candidate = _safe_date(as_of.year + 1, month, day)
        return candidate

    if match := _MONTH_RE.match(text):
        month = _MONTHS.get(match.group(2))
        if month is None:
            return None
        day_raw = match.group(1) or match.group(3)
        year = _full_year(match.group(4))
        if year is None:
            year = as_of.year if month >= as_of.month else as_of.year + 1
        if day_raw:
            return _safe_date(year, month, int(day_raw))
        return _third_friday(year, month)

    return None


def match_expiration(target: date, expirations: list[str]) -> str | None:
    """The listed expiration (``YYYY-MM-DD``) closest to *target*, if near."""
    best: tuple[timedelta, str] | None = None
    for raw in expirations:
        try:
            listed = date.fromisoformat(raw)
        except ValueError:
            continue
        gap = abs(listed - target)
        if gap <= _MATCH_WINDOW and (best is None or gap < best[0]):
            best = (gap, raw)
    return best[1] if best else None


async def get_option_contract(
    symbol: str,
    right: str,
    strike: float,
    expiry: str,
    as_of: date | None = None,
    today: date | None = None,
) -> dict | None:
    """Current quote for one contract, or None when it can't be identified.

    An expiry already in the past gives ``status: "expired"`` without a quote.
    """
    symbol = (symbol or "").strip().upper()
    right = (right or "").strip().upper()
    if not symbol or right not in {"CALL", "PUT"}:
        return None

    today = today or date.today()
    target = parse_expiry(expiry, as_of or today)
    if target is None:
        return None

    base = {"symbol": symbol, "right": right, "strike": strike}
    if target < today:
        return {**base, "status": "expired", "expiration": target.isoformat()}

    chain = await get_options_chain(symbol)
    if chain is None:
        return None
    expiration = match_expiration(target, chain.get("expirations") or [])
    if expiration is None:
        return None
    if chain.get("expiration") != expiration:
        chain = await get_options_chain(symbol, expiration)
        if chain is None or chain.get("expiration") != expiration:
            return None

    contract = next(
        (
            c
            for c in chain.get("contracts") or []
            if c.get("option_type") == right
            and c.get("strike") is not None
            and abs(c["strike"] - strike) < 1e-6
        ),
        None,
    )
    if contract is None:
        return None

    bid, ask = contract.get("bid"), contract.get("ask")
    mid = round((bid + ask) / 2, 4) if bid and ask else None
    return {
        **base,
        "status": "listed",
        "expiration": expiration,
        "last_price": contract.get("last_price"),
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "change_percent": contract.get("change_percent"),
        "implied_volatility": contract.get("implied_volatility"),
        "volume": contract.get("volume"),
        "open_interest": contract.get("open_interest"),
        "in_the_money": contract.get("in_the_money"),
        "underlying_price": (chain.get("underlying") or {}).get("last_price"),
    }
