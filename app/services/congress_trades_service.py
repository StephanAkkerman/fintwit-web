"""Stock trades disclosed by members of the US Congress (fintwit-bot issue #632).

Members must report trades above $1,000 within 45 days under the STOCK Act.
The issue mainly asks for Nancy Pelosi's trades and lists the trackers that
republish the filings (Quiver, Capitol Trades, Unusual Whales, ...). Every API
among them needs a key, and Capitol Trades sits behind a bot checkpoint, but
Quiver's public congress-trading page embeds its latest ~300 disclosures as a
JavaScript array (`recentTradesData`) that this module reads. That page is
scraped, so it can change without notice. When it does, the service returns
``None`` and the widget shows its unavailable state.

Each embedded row is positional::

    [ticker, asset name, asset type, transaction, amount range, politician,
     chamber, party, filed, traded, description, id, excess return %,
     full name, photo url, bioguide id]

Amounts are only disclosed as ranges, and "excess return" is Quiver's estimate
of the stock's move since the trade minus the market's.
"""

from __future__ import annotations

import ast
import logging
import re
import time
from collections import Counter, defaultdict
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

_QUIVER_URL = "https://www.quiverquant.com/congresstrading/"
_POLITICIAN_URL = "https://www.quiverquant.com/congresstrading/politician/{slug}"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}
_DATA_MARKER = "recentTradesData = "
_CACHE_TTL_SECONDS = 3600  # filings trickle in a few times a day
_ROW_FIELDS = 16

#: Most bought/sold tickers returned in the summary.
TOP_TICKERS = 8
#: Most active politicians returned in the summary.
TOP_POLITICIANS = 12

_TRANSACTIONS = {
    "purchase": "buy",
    "sale": "sell",
    "sale (partial)": "sell",
    "sale (full)": "sell",
    "exchange": "exchange",
}
_PARTIES = {"D": "Democrat", "R": "Republican", "I": "Independent"}

_cache: tuple[float, dict] | None = None


def _reset_cache_for_tests() -> None:
    global _cache
    _cache = None


def extract_rows(html: str) -> list[list] | None:
    """Pull the ``recentTradesData`` array out of the page.

    Scans for the bracket that closes the array, skipping brackets inside
    quoted strings (descriptions can contain them), then parses it as a
    Python literal: the page writes it with single-quoted strings.

    :return: the raw rows, or ``None`` when the array is missing or unparsable.
    """
    start = html.find(_DATA_MARKER)
    if start < 0:
        return None
    start += len(_DATA_MARKER)
    if start >= len(html) or html[start] != "[":
        return None

    depth = 0
    quote_char: str | None = None
    escaped = False
    end = None
    for i in range(start, len(html)):
        char = html[i]
        if quote_char:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote_char:
                quote_char = None
            continue
        if char in ("'", '"'):
            quote_char = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        return None

    try:
        rows = ast.literal_eval(html[start:end])
    except (ValueError, SyntaxError) as exc:
        logger.warning("[congress] could not parse Quiver's trade data: %r", exc)
        return None
    return rows if isinstance(rows, list) else None


def _text(value: object) -> str | None:
    text = " ".join(str(value).split()) if value is not None else ""
    return text if text and text != "-" else None


def _date(value: object) -> str | None:
    text = _text(value)
    return text[:10] if text else None


def _float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def parse_amount(text: str | None) -> tuple[int | None, int | None]:
    """``"$1,001 - $15,000"`` -> ``(1001, 15000)``; open-ended tops are None."""
    if not text:
        return None, None
    numbers = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", text)]
    if not numbers:
        return None, None
    if len(numbers) == 1:
        return numbers[0], None
    return numbers[0], numbers[1]


def _politician_url(name: str, bioguide: str | None) -> str | None:
    if not bioguide:
        return None
    return _POLITICIAN_URL.format(slug=quote(f"{name}-{bioguide}"))


def parse_trade(row: list) -> dict | None:
    """Map one positional Quiver row to a trade dict, or ``None`` if malformed."""
    if not isinstance(row, (list, tuple)) or len(row) < _ROW_FIELDS:
        return None
    politician = _text(row[5])
    transaction_label = _text(row[3])
    if not politician or not transaction_label:
        return None

    ticker = _text(row[0])
    amount_range = _text(row[4])
    amount_min, amount_max = parse_amount(amount_range)
    party = _text(row[7])
    bioguide = _text(row[15])
    return {
        "id": _text(row[11]),
        "ticker": ticker.upper() if ticker else None,
        "asset": _text(row[1]),
        "asset_type": _text(row[2]),
        "transaction": _TRANSACTIONS.get(transaction_label.lower(), "other"),
        "transaction_label": transaction_label,
        "amount_range": amount_range,
        "amount_min": amount_min,
        "amount_max": amount_max,
        "politician": politician,
        "chamber": _text(row[6]),
        "party": party,
        "party_name": _PARTIES.get(party or ""),
        "filed": _date(row[8]),
        "traded": _date(row[9]),
        "description": _text(row[10]),
        "excess_return_pct": _float(row[12]),
        "photo_url": _text(row[14]),
        "bioguide_id": bioguide,
        "website": _politician_url(politician, bioguide),
    }


def summarize(trades: list[dict]) -> dict:
    """Most bought/sold tickers and most active politicians in ``trades``."""
    flows: dict[str, dict[str, Counter]] = {
        "buy": defaultdict(Counter),
        "sell": defaultdict(Counter),
    }
    for trade in trades:
        side = trade["transaction"]
        if trade["ticker"] and side in flows:
            flows[side][trade["ticker"]][trade["politician"]] += 1

    def top(side: str) -> list[dict]:
        ranked = sorted(
            flows[side].items(),
            # Several members trading a name says more than one member's
            # rebalancing, so breadth ranks ahead of the trade count.
            key=lambda item: (-len(item[1]), -sum(item[1].values()), item[0]),
        )
        return [
            {
                "ticker": ticker,
                "trades": sum(by_politician.values()),
                "politicians": sorted(by_politician),
            }
            for ticker, by_politician in ranked[:TOP_TICKERS]
        ]

    activity: dict[str, dict] = {}
    for trade in trades:
        entry = activity.setdefault(
            trade["politician"],
            {
                "name": trade["politician"],
                "party": trade["party"],
                "chamber": trade["chamber"],
                "trades": 0,
                "buys": 0,
                "sells": 0,
                "last_filed": None,
            },
        )
        entry["trades"] += 1
        if trade["transaction"] == "buy":
            entry["buys"] += 1
        elif trade["transaction"] == "sell":
            entry["sells"] += 1
        if trade["filed"] and (
            entry["last_filed"] is None or trade["filed"] > entry["last_filed"]
        ):
            entry["last_filed"] = trade["filed"]
    politicians = sorted(activity.values(), key=lambda p: (-p["trades"], p["name"]))

    return {
        "trades": len(trades),
        "buys": sum(1 for t in trades if t["transaction"] == "buy"),
        "sells": sum(1 for t in trades if t["transaction"] == "sell"),
        "most_bought": top("buy"),
        "most_sold": top("sell"),
        "politicians": politicians[:TOP_POLITICIANS],
    }


async def _fetch_all(client: httpx.AsyncClient) -> list[dict] | None:
    global _cache
    if _cache and time.time() - _cache[0] <= _CACHE_TTL_SECONDS:
        return _cache[1]["trades"]
    try:
        response = await client.get(_QUIVER_URL, headers=_HEADERS, timeout=20)
    except httpx.RequestError as exc:
        logger.warning("[congress] Quiver request failed: %r", exc)
        return None
    if response.status_code != 200:
        logger.warning("[congress] Quiver returned status=%s", response.status_code)
        return None
    rows = extract_rows(response.text)
    if rows is None:
        logger.warning("[congress] trade data not found on Quiver's page")
        return None
    trades = [t for t in map(parse_trade, rows) if t is not None]
    # Newest filing first; within a filing, newest trade first.
    trades.sort(key=lambda t: (t["filed"] or "", t["traded"] or ""), reverse=True)
    _cache = (time.time(), {"trades": trades})
    return trades


async def get_congress_trades(
    client: httpx.AsyncClient,
    politician: str | None = None,
    stocks_only: bool = True,
    limit: int = 50,
) -> dict | None:
    """Recent congressional trade disclosures, newest filing first.

    :param politician: case-insensitive substring of the member's name.
    :param stocks_only: drop rows without a ticker (bonds, funds, LLC stakes).
    :param limit: trades returned; the summary covers every matching trade.
    :return: ``{trades, summary, filter, as_of, source}``, or ``None`` when
        Quiver's page could not be read.
    """
    trades = await _fetch_all(client)
    if trades is None:
        return None

    needle = (politician or "").strip().lower()
    matching = [
        t
        for t in trades
        if (not stocks_only or t["ticker"])
        and (not needle or needle in t["politician"].lower())
    ]
    bounded_limit = max(1, min(int(limit), 300))
    return {
        "trades": matching[:bounded_limit],
        "summary": summarize(matching),
        "filter": {"politician": politician or None, "stocks_only": stocks_only},
        "as_of": max((t["filed"] for t in trades if t["filed"]), default=None),
        "source": "quiver",
    }
