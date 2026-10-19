"""Open-market stock trades by company insiders (SEC Form 4).

Officers, directors and 10% owners must report a trade in their company's
stock within two business days on SEC Form 4. Sales are common and mostly
noise (pay, taxes, diversification); purchases with their own money are rare,
and several insiders buying the same stock at once ("cluster buys") is one of
the better-documented signals in the filings.

EDGAR publishes each Form 4 as its own XML document, so building a market-wide
feed from it means fetching thousands of filings a day. OpenInsider already
parses them into one screener table, with a link back to each SEC filing, so
this module reads that table instead. It is a scraped HTML page: when its
layout changes the service returns ``None`` and the widget shows its
unavailable state.

Only open-market purchases (``P``) and sales (``S``) are requested; grants,
option exercises and tax withholding are left out. A sale reported together
with an option exercise (``Sale+OE``) is flagged, because it is usually
compensation being cashed out rather than a view on the stock.
"""

from __future__ import annotations

import html
import logging
import re
import time
from collections import defaultdict

import httpx

logger = logging.getLogger(__name__)

_SCREENER_URL = "http://openinsider.com/screener"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}
_CACHE_TTL_SECONDS = 1800  # Form 4s trickle in through the day
_MAX_ROWS = 5000
#: OpenInsider prints an overflowed int32 for values it could not compute.
_OVERFLOW = 2_147_483_647

#: Cluster buys, biggest buys and biggest sales returned in the summary.
TOP_N = 10

_ROW_RE = re.compile(r'<tr style="background:[^"]*">(.*?)</tr>', re.S)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_HREF_RE = re.compile(r'href="([^"]+)"')
_TICKER_RE = re.compile(r'<a href="/([A-Z0-9.\-]+)"')
_TAG_RE = re.compile(r"<[^>]+>")
_HEADER_RE = re.compile(r"<th[^>]*><h3>(.*?)</h3></th>", re.S)
#: Screener columns by header text. A one-ticker screen drops "Company Name".
_COLUMNS = {
    "X": "remarks",
    "Filing Date": "filed_at",
    "Trade Date": "traded",
    "Ticker": "ticker",
    "Company Name": "company",
    "Insider Name": "insider",
    "Title": "title",
    "Trade Type": "trade_type",
    "Price": "price",
    "Qty": "shares",
    "Owned": "owned",
    "ΔOwn": "delta_own",
    "Value": "value",
}
_REQUIRED = {"filed_at", "traded", "ticker", "insider", "trade_type", "value"}

#: OpenInsider's "X" column: one letter per remark on the filing.
_REMARKS = {
    "A": "amended",
    "D": "derivative",
    "E": "error_detected",
    "M": "multiple_transactions",
}
#: Title fragments ranked as the most informed insiders.
_OFFICER_TITLES = ("CEO", "CFO", "COO", "PRES", "COB", "CHAIR")

_cache: dict[tuple, tuple[float, dict]] = {}


def _reset_cache_for_tests() -> None:
    _cache.clear()


def _text(cell: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub("", cell)).split())


def _number(text: str) -> float | None:
    """``"+$1,234"`` / ``"-22,500"`` / ``"$2.11"`` / ``"+2%"`` -> float."""
    cleaned = text.replace("$", "").replace(",", "").replace("%", "").strip()
    if not cleaned or cleaned in ("+", "-") or cleaned.lower() == "new":
        return None
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return None if abs(number) >= _OVERFLOW else number


def _is_officer(title: str | None) -> bool:
    upper = (title or "").upper()
    return any(fragment in upper for fragment in _OFFICER_TITLES)


def parse_columns(page: str) -> dict[str, int] | None:
    """Column positions in the screener table, keyed by field name."""
    columns = {}
    for index, header in enumerate(_HEADER_RE.findall(page)):
        field = _COLUMNS.get(_text(header))
        if field:
            columns.setdefault(field, index)
    return columns if _REQUIRED <= columns.keys() else None


def parse_row(row_html: str, columns: dict[str, int]) -> dict | None:
    """Map one screener table row to a trade dict, or ``None`` if malformed."""
    raw = _CELL_RE.findall(row_html)
    if len(raw) <= max(columns.values()):
        return None
    cells = {field: "" for field in _COLUMNS.values()}
    cells.update({field: raw[index] for field, index in columns.items()})
    # The ticker cell carries a chart tooltip with markup inside an attribute,
    # so read the ticker from its link instead of stripping tags.
    ticker_link = _TICKER_RE.search(cells["ticker"])
    ticker = ticker_link.group(1) if ticker_link else ""
    trade_label = _text(cells["trade_type"])
    code = trade_label[:1]
    if not ticker or code not in ("P", "S"):
        return None

    filing_link = _HREF_RE.search(cells["filed_at"])
    insider_link = _HREF_RE.search(cells["insider"])
    insider_cik = None
    if insider_link:
        tail = insider_link.group(1).rstrip("/").rsplit("/", 1)[-1]
        insider_cik = tail if tail.isdigit() else None
    title = _text(cells["title"]) or None
    delta_own_text = _text(cells["delta_own"])
    return {
        "filed_at": _text(cells["filed_at"]) or None,
        "traded": _text(cells["traded"]) or None,
        "ticker": ticker,
        "company": _text(cells["company"]) or None,
        "insider": _text(cells["insider"]) or None,
        "insider_cik": insider_cik,
        "title": title,
        "is_officer": _is_officer(title),
        "is_ten_percent_owner": "10%" in (title or ""),
        "side": "buy" if code == "P" else "sell",
        "trade_label": trade_label,
        "with_option_exercise": "+OE" in trade_label,
        "price": _number(_text(cells["price"])),
        "shares": _number(_text(cells["shares"])),
        "owned_after": _number(_text(cells["owned"])),
        "owned_change_pct": _number(delta_own_text),
        "new_position": delta_own_text.lower() == "new",
        "value": _number(_text(cells["value"])),
        "remarks": [_REMARKS[c] for c in _text(cells["remarks"]) if c in _REMARKS],
        "filing_url": filing_link.group(1) if filing_link else None,
    }


def extract_trades(page: str) -> list[dict] | None:
    """All trades in a screener page, or ``None`` when its table is missing."""
    if 'class="tinytable"' not in page:
        return None
    columns = parse_columns(page)
    if columns is None:
        return None
    rows = (parse_row(row, columns) for row in _ROW_RE.findall(page))
    return [t for t in rows if t is not None]


def _group(trades: list[dict], side: str) -> list[dict]:
    """One entry per ticker: insiders, trade count and total value on ``side``."""
    groups: dict[str, dict] = {}
    for trade in trades:
        if trade["side"] != side:
            continue
        entry = groups.setdefault(
            trade["ticker"],
            {
                "ticker": trade["ticker"],
                "company": trade["company"],
                "insiders": set(),
                "officers": set(),
                "trades": 0,
                "value": 0.0,
                "last_traded": None,
                "last_price": None,
            },
        )
        entry["insiders"].add(trade["insider"])
        if trade["is_officer"]:
            entry["officers"].add(trade["insider"])
        entry["trades"] += 1
        entry["value"] += abs(trade["value"] or 0.0)
        if trade["traded"] and (
            entry["last_traded"] is None or trade["traded"] > entry["last_traded"]
        ):
            entry["last_traded"] = trade["traded"]
            entry["last_price"] = trade["price"]
    return [
        {
            **entry,
            "insiders": sorted(i for i in entry["insiders"] if i),
            "officers": sorted(i for i in entry["officers"] if i),
            "value": round(entry["value"], 2),
        }
        for entry in groups.values()
    ]


def summarize(trades: list[dict]) -> dict:
    """Cluster buys, the biggest buys and sales, and the buy/sell balance.

    Sales tied to an option exercise are left out of ``top_sells``: they are
    mostly pay being cashed out.
    """
    buys = _group(trades, "buy")
    cluster_buys = sorted(
        (g for g in buys if len(g["insiders"]) >= 2),
        key=lambda g: (-len(g["insiders"]), -g["value"], g["ticker"]),
    )
    top_buys = sorted(buys, key=lambda g: (-g["value"], g["ticker"]))
    plain_sales = [t for t in trades if not t["with_option_exercise"]]
    top_sells = sorted(
        _group(plain_sales, "sell"), key=lambda g: (-g["value"], g["ticker"])
    )

    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for trade in trades:
        totals[trade["side"]] += abs(trade["value"] or 0.0)
        counts[trade["side"]] += 1
    buy_value, sell_value = totals["buy"], totals["sell"]
    return {
        "buys": counts["buy"],
        "sells": counts["sell"],
        "buy_value": round(buy_value, 2),
        "sell_value": round(sell_value, 2),
        "buy_share_pct": (
            round(buy_value / (buy_value + sell_value) * 100, 1)
            if buy_value + sell_value
            else None
        ),
        "cluster_buys": cluster_buys[:TOP_N],
        "top_buys": top_buys[:TOP_N],
        "top_sells": top_sells[:TOP_N],
    }


def _screener_params(days: int, min_value: int, ticker: str | None) -> dict:
    return {
        "s": ticker or "",
        "fd": days,  # filed in the last N days
        "xp": 1,  # purchases
        "xs": 1,  # sales
        "vl": max(0, min_value // 1000),  # minimum value, in $k
        "sortcol": 0,  # newest filing first
        "cnt": _MAX_ROWS,
        "page": 1,
    }


async def get_insider_trades(
    client: httpx.AsyncClient,
    days: int = 30,
    min_value: int = 25_000,
    ticker: str | None = None,
    side: str | None = None,
    limit: int = 100,
) -> dict | None:
    """Recent insider purchases and sales, newest filing first.

    :param days: filing-date window.
    :param min_value: drop trades below this dollar value.
    :param ticker: one company's trades only.
    :param side: ``buy`` or ``sell`` to filter ``trades`` (the summary covers both).
    :param limit: trades returned; the summary covers every trade in the window.
    :return: ``{trades, summary, filter, as_of, source}``, or ``None`` when the
        screener could not be read.
    """
    days = max(1, min(int(days), 365))
    min_value = max(0, int(min_value))
    ticker = (ticker or "").strip().upper() or None
    key = (days, min_value // 1000, ticker)

    cached = _cache.get(key)
    if cached and time.time() - cached[0] <= _CACHE_TTL_SECONDS:
        trades = cached[1]["trades"]
    else:
        try:
            response = await client.get(
                _SCREENER_URL,
                params=_screener_params(days, min_value, ticker),
                headers=_HEADERS,
                timeout=30,
            )
        except httpx.RequestError as exc:
            logger.warning("[insider] OpenInsider request failed: %r", exc)
            return None
        if response.status_code != 200:
            logger.warning(
                "[insider] OpenInsider returned status=%s", response.status_code
            )
            return None
        trades = extract_trades(response.text)
        if trades is None:
            logger.warning("[insider] trade table not found on OpenInsider's page")
            return None
        _cache[key] = (time.time(), {"trades": trades})

    matching = [t for t in trades if side not in ("buy", "sell") or t["side"] == side]
    return {
        "trades": matching[: max(1, min(int(limit), _MAX_ROWS))],
        "summary": summarize(trades),
        "filter": {
            "days": days,
            "min_value": min_value,
            "ticker": ticker,
            "side": side if side in ("buy", "sell") else None,
        },
        "as_of": max((t["filed_at"] for t in trades if t["filed_at"]), default=None),
        "source": "openinsider",
    }
