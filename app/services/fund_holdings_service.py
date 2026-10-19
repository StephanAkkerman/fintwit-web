"""What well-known funds bought and sold last quarter, from their SEC 13F filings.

Every investment manager with over $100M in US equities files a 13F-HR within
45 days of each quarter end, listing its long stock and listed-option
positions. Comparing a fund's two latest filings shows what it opened, added
to, trimmed and sold out of, and comparing across funds shows which names
several of them moved into at once (fintwit-bot issue #190 asked for the
holdings of big investors).

The filings come straight from SEC EDGAR (no key): the submissions index per
fund, then each filing's information table XML. 13F rows identify a security
only by CUSIP, so tickers come from OpenFIGI's free mapping API, with every
answer stored in the database because the free tier allows 25 requests a
minute.

Caveats worth showing next to the data: 13Fs are a quarter old by the time
they are filed, list long positions only (no shorts, no cash, no non-US
listings), and an option row is the value of the underlying shares, not of the
contracts.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from typing import Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_FILING_INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/index.json"
)
_FILING_FILE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{name}"
_FILING_PAGE_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{dashed}-index.html"
)
_OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
#: SEC's fair-access policy asks automated clients to name themselves and a
#: contact email, and www.sec.gov refuses requests without an email. Set
#: ``SEC_USER_AGENT`` to your own "name email"; this placeholder only keeps a
#: fresh install working.
_DEFAULT_USER_AGENT = "fintwit-web admin@example.com"
#: SEC allows 10 requests a second.
_SEC_CONCURRENCY = 4
_CACHE_TTL_SECONDS = 24 * 3600  # filings land quarterly; a worker refreshes it
#: A fund whose latest filing is older than this has likely stopped filing.
STALE_AFTER_DAYS = 250

#: (CIK, fund, manager). Long-only and concentrated books read best; a fund
#: can be added with ``FUND_HOLDINGS_EXTRA_CIKS``.
FUNDS: list[tuple[int, str, str]] = [
    (1067983, "Berkshire Hathaway", "Warren Buffett"),
    (1336528, "Pershing Square", "Bill Ackman"),
    (1536411, "Duquesne Family Office", "Stanley Druckenmiller"),
    (1656456, "Appaloosa", "David Tepper"),
    (1040273, "Third Point", "Dan Loeb"),
    (1061768, "Baupost Group", "Seth Klarman"),
    (921669, "Icahn Capital", "Carl Icahn"),
    (1029160, "Soros Fund Management", "George Soros"),
    (1350694, "Bridgewater Associates", "Ray Dalio"),
    (1167483, "Tiger Global", "Chase Coleman"),
    (1135730, "Coatue Management", "Philippe Laffont"),
    (1061165, "Lone Pine Capital", "Stephen Mandel"),
    (1103804, "Viking Global", "Andreas Halvorsen"),
    (1697748, "ARK Investment Management", "Cathie Wood"),
]

#: Rows returned per fund and in the cross-fund lists.
TOP_HOLDINGS = 15
TOP_CHANGES = 10
TOP_ACROSS = 15
#: A share count change below this is treated as unchanged (rounding, splits).
_MIN_CHANGE_PCT = 2.0

_NS = {"t": "http://www.sec.gov/edgar/document/thirteenf/informationtable"}

#: Maps CUSIPs to ``{cusip: {"ticker", "name"}}``; returns what it could map.
CusipMapper = Callable[[list[str]], Awaitable[dict[str, dict]]]

_cache: tuple[float, dict] | None = None
_lock = asyncio.Lock()


def _reset_cache_for_tests() -> None:
    global _cache
    _cache = None


def _user_agent() -> str:
    return os.getenv("SEC_USER_AGENT", "").strip() or _DEFAULT_USER_AGENT


def funds() -> list[tuple[int, str | None, str | None]]:
    """The tracked funds: the defaults plus ``FUND_HOLDINGS_EXTRA_CIKS``."""
    tracked: list[tuple[int, str | None, str | None]] = list(FUNDS)
    known = {cik for cik, *_ in tracked}
    for part in os.getenv("FUND_HOLDINGS_EXTRA_CIKS", "").split(","):
        part = part.strip()
        if part.isdigit() and int(part) not in known:
            tracked.append((int(part), None, None))
            known.add(int(part))
    return tracked


def latest_13f_filings(submissions: dict, count: int = 2) -> list[dict]:
    """The newest original 13F-HR filings (amendments skipped), newest first."""
    recent = (submissions.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    filings = []
    for i, form in enumerate(forms):
        if form != "13F-HR":
            continue
        filings.append(
            {
                "accession": recent["accessionNumber"][i],
                "report_date": recent["reportDate"][i],
                "filed": recent["filingDate"][i],
            }
        )
        if len(filings) == count:
            break
    return filings


def parse_information_table(xml_text: str, report_date: str) -> dict[tuple, dict]:
    """Positions keyed by ``(cusip, instrument)``, summed across managers.

    ``instrument`` is ``None`` for shares, ``call`` or ``put`` for listed
    options and ``note`` for convertible notes (amounts in principal).

    Values are in dollars since 2023, but some filers (and every filing before)
    still report thousands; :func:`_dollar_scale` detects which.
    """
    root = ET.fromstring(xml_text)
    positions: dict[tuple, dict] = {}
    for row in root.iter(f"{{{_NS['t']}}}infoTable"):

        def field(path: str) -> str | None:
            node = row.find(path, _NS)
            return node.text.strip() if node is not None and node.text else None

        cusip = (field("t:cusip") or "").upper()
        if not cusip:
            continue
        instrument = (field("t:putCall") or "").lower() or None
        if instrument is None and field("t:shrsOrPrnAmt/t:sshPrnamtType") == "PRN":
            instrument = "note"
        key = (cusip, instrument)
        entry = positions.setdefault(
            key,
            {
                "cusip": cusip,
                "issuer": field("t:nameOfIssuer"),
                "title_of_class": field("t:titleOfClass"),
                "instrument": instrument,
                "value": 0.0,
                "shares": 0.0,
            },
        )
        try:
            entry["value"] += float(field("t:value") or 0)
            entry["shares"] += float(field("t:shrsOrPrnAmt/t:sshPrnamt") or 0)
        except ValueError:
            continue
    scale = _dollar_scale(list(positions.values()), report_date)
    if scale != 1:
        for entry in positions.values():
            entry["value"] *= scale
    return positions


def _dollar_scale(positions: list[dict], report_date: str) -> int:
    """1 when values are in dollars, 1000 when they are in thousands.

    Judged from the median implied share price: a book of stocks whose median
    price is under $1 is far likelier to be reported in thousands.
    """
    prices = sorted(
        p["value"] / p["shares"]
        for p in positions
        if p["shares"] and not p["instrument"]
    )
    if not prices:
        return 1000 if report_date < "2023-01-01" else 1
    return 1000 if prices[len(prices) // 2] < 1.0 else 1


def diff_positions(
    current: dict[tuple, dict], previous: dict[tuple, dict]
) -> list[dict]:
    """Every position with its quarter-over-quarter change.

    ``action`` is ``new``, ``added``, ``reduced``, ``sold_out`` or ``unchanged``.
    """
    total = sum(p["value"] for p in current.values()) or 1.0
    rows = []
    for key in current.keys() | previous.keys():
        now, before = current.get(key), previous.get(key)
        shares = now["shares"] if now else 0.0
        prev_shares = before["shares"] if before else 0.0
        if before is None:
            action, change_pct = "new", None
        elif now is None:
            action, change_pct = "sold_out", -100.0
        else:
            change_pct = (
                round((shares - prev_shares) / prev_shares * 100, 1)
                if prev_shares
                else None
            )
            if change_pct is None or abs(change_pct) < _MIN_CHANGE_PCT:
                action = "unchanged"
            else:
                action = "added" if change_pct > 0 else "reduced"
        base = now or before
        value = now["value"] if now else 0.0
        prev_value = before["value"] if before else 0.0
        # Price the share change at this quarter's price (last quarter's for a
        # sale), so a move in the stock alone doesn't read as buying.
        price = (
            value / shares
            if shares
            else (prev_value / prev_shares if prev_shares else 0.0)
        )
        rows.append(
            {
                "cusip": base["cusip"],
                "issuer": base["issuer"],
                "instrument": base["instrument"],
                "value": round(value, 2),
                "shares": shares,
                "prev_shares": prev_shares,
                "weight_pct": round(value / total * 100, 2),
                "action": action,
                "shares_change_pct": change_pct,
                "value_change": round((shares - prev_shares) * price, 2),
            }
        )
    return rows


def summarize_fund(rows: list[dict]) -> dict:
    """Top holdings, biggest buys and biggest sales for one fund."""
    held = [r for r in rows if r["action"] != "sold_out"]
    buys = [r for r in rows if r["action"] in ("new", "added")]
    sells = [r for r in rows if r["action"] in ("reduced", "sold_out")]
    return {
        "positions": len(held),
        "total_value": round(sum(r["value"] for r in held), 2),
        "top_holdings": sorted(held, key=lambda r: -r["value"])[:TOP_HOLDINGS],
        "buys": sorted(buys, key=lambda r: -r["value_change"])[:TOP_CHANGES],
        "sells": sorted(sells, key=lambda r: r["value_change"])[:TOP_CHANGES],
        "new_positions": sum(1 for r in rows if r["action"] == "new"),
        "sold_out": sum(1 for r in rows if r["action"] == "sold_out"),
    }


def summarize_across(fund_rows: dict[str, list[dict]]) -> dict:
    """Stocks several funds moved into or out of, and the most widely held.

    Option rows are left out: a call or put is a different bet from the stock.
    """
    moves: dict[str, dict[str, dict]] = {"buy": {}, "sell": {}}
    held: dict[str, dict] = {}
    for fund, rows in fund_rows.items():
        for row in rows:
            if row["instrument"]:
                continue
            side = (
                "buy"
                if row["action"] in ("new", "added")
                else "sell"
                if row["action"] in ("reduced", "sold_out")
                else None
            )
            if side:
                entry = moves[side].setdefault(
                    row["cusip"],
                    {
                        "cusip": row["cusip"],
                        "issuer": row["issuer"],
                        "funds": [],
                        "new_or_exited": 0,
                        "value_change": 0.0,
                    },
                )
                entry["funds"].append(fund)
                entry["value_change"] += row["value_change"]
                if row["action"] in ("new", "sold_out"):
                    entry["new_or_exited"] += 1
            if row["action"] != "sold_out":
                entry = held.setdefault(
                    row["cusip"],
                    {
                        "cusip": row["cusip"],
                        "issuer": row["issuer"],
                        "funds": [],
                        "value": 0.0,
                    },
                )
                entry["funds"].append(fund)
                entry["value"] += row["value"]

    def ranked(entries: dict[str, dict], key: str) -> list[dict]:
        rows = sorted(
            entries.values(),
            # Breadth first: several funds agreeing says more than one big trade.
            key=lambda e: (-len(e["funds"]), -abs(e[key]), e["issuer"] or ""),
        )
        return [
            {**e, "funds": sorted(e["funds"]), key: round(e[key], 2)}
            for e in rows[:TOP_ACROSS]
        ]

    return {
        "most_bought": ranked(moves["buy"], "value_change"),
        "most_sold": ranked(moves["sell"], "value_change"),
        "most_held": ranked(held, "value"),
    }


class _Sec:
    """EDGAR client: identifies itself and stays under SEC's request rate."""

    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.limiter = asyncio.Semaphore(_SEC_CONCURRENCY)

    async def get(self, url: str) -> httpx.Response | None:
        async with self.limiter:
            try:
                response = await self.client.get(
                    url, headers={"User-Agent": _user_agent()}, timeout=30
                )
            except httpx.RequestError as exc:
                logger.warning("[13f] request failed %s: %r", url, exc)
                return None
            finally:
                await asyncio.sleep(0.15)
        if response.status_code != 200:
            logger.warning("[13f] %s returned status=%s", url, response.status_code)
            return None
        return response


async def _information_table(sec: _Sec, cik: int, filing: dict) -> dict | None:
    accession = filing["accession"].replace("-", "")
    index = await sec.get(_FILING_INDEX_URL.format(cik=cik, accession=accession))
    if index is None:
        return None
    try:
        items = index.json()["directory"]["item"]
    except (ValueError, KeyError, TypeError):
        return None
    # The information table is the filing's XML other than the cover page.
    names = [
        item["name"]
        for item in items
        if item.get("name", "").lower().endswith(".xml")
        and item["name"].lower() != "primary_doc.xml"
    ]
    for name in names:
        response = await sec.get(
            _FILING_FILE_URL.format(cik=cik, accession=accession, name=name)
        )
        if response is None or "informationTable" not in response.text[:2000]:
            continue
        try:
            return parse_information_table(response.text, filing["report_date"])
        except ET.ParseError as exc:
            logger.warning("[13f] could not parse %s/%s: %r", cik, name, exc)
    return None


async def _fund(
    sec: _Sec, cik: int, name: str | None, manager: str | None
) -> dict | None:
    response = await sec.get(_SUBMISSIONS_URL.format(cik=cik))
    if response is None:
        return None
    try:
        submissions = response.json()
    except ValueError:
        return None
    filings = latest_13f_filings(submissions)
    if not filings:
        return None
    tables = await asyncio.gather(*(_information_table(sec, cik, f) for f in filings))
    current = tables[0]
    if current is None:
        return None
    previous = tables[1] if len(tables) > 1 and tables[1] is not None else {}
    latest = filings[0]
    accession = latest["accession"].replace("-", "")
    return {
        "cik": cik,
        "name": name or str(submissions.get("name") or cik).title(),
        "manager": manager,
        "report_date": latest["report_date"],
        "filed": latest["filed"],
        "prev_report_date": filings[1]["report_date"] if len(filings) > 1 else None,
        "filing_url": _FILING_PAGE_URL.format(
            cik=cik, accession=accession, dashed=latest["accession"]
        ),
        "rows": diff_positions(current, previous),
    }


def _attach_tickers(rows: list[dict], tickers: dict[str, dict]) -> None:
    for row in rows:
        mapped = tickers.get(row["cusip"]) or {}
        row["ticker"] = mapped.get("ticker")


async def build_fund_holdings(
    client: httpx.AsyncClient, map_cusips: CusipMapper, today: str
) -> dict | None:
    """Fetch every tracked fund's two latest 13Fs and summarise them."""
    sec = _Sec(client)
    tracked = funds()
    results = await asyncio.gather(*(_fund(sec, *fund) for fund in tracked))
    loaded = [r for r in results if r is not None]
    if not loaded:
        return None

    fund_rows = {fund["name"]: fund.pop("rows") for fund in loaded}
    summaries = []
    for fund in loaded:
        summary = summarize_fund(fund_rows[fund["name"]])
        age_days = (
            _days_between(fund["report_date"], today) if fund["report_date"] else None
        )
        summaries.append(
            {
                **fund,
                **summary,
                "stale": age_days is not None and age_days > STALE_AFTER_DAYS,
            }
        )
    across = summarize_across(
        {s["name"]: fund_rows[s["name"]] for s in summaries if not s["stale"]}
    )

    shown = [
        row
        for fund in summaries
        for key in ("top_holdings", "buys", "sells")
        for row in fund[key]
    ] + [row for key in across for row in across[key]]
    tickers = await map_cusips(sorted({row["cusip"] for row in shown}))
    _attach_tickers(shown, tickers)

    summaries.sort(key=lambda f: -f["total_value"])
    return {
        "funds": summaries,
        **across,
        "report_date": max((f["report_date"] for f in summaries), default=None),
        "missing": [
            name or str(cik)
            for cik, name, _ in tracked
            if cik not in {f["cik"] for f in loaded}
        ],
        "source": "sec-13f",
    }


def _days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


async def get_fund_holdings(
    client: httpx.AsyncClient, map_cusips: CusipMapper, refresh: bool = False
) -> dict | None:
    """Tracked funds' latest 13F holdings and quarter changes. 24-hour cache.

    :param refresh: rebuild even when the cache is fresh (the refresh worker).

    :return: ``{funds, most_bought, most_sold, most_held, report_date, missing,
        as_of, source}``, or ``None`` when no fund's filings could be read.
    """
    global _cache
    async with _lock:
        if not refresh and _cache and time.time() - _cache[0] <= _CACHE_TTL_SECONDS:
            return _cache[1]
        now = datetime.now(timezone.utc)
        data = await build_fund_holdings(client, map_cusips, now.date().isoformat())
        if data is not None:
            data["as_of"] = now.isoformat()
            _cache = (time.time(), data)
        return data


async def _figi_pass(
    client: httpx.AsyncClient, cusips: list[str], us_only: bool
) -> dict[str, dict] | None:
    """One OpenFIGI mapping pass; ``None`` when OpenFIGI could not be reached."""
    api_key = os.getenv("OPENFIGI_API_KEY", "").strip()
    batch_size = 100 if api_key else 10
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-OPENFIGI-APIKEY"] = api_key

    found: dict[str, dict] = {}
    for start in range(0, len(cusips), batch_size):
        batch = cusips[start : start + batch_size]
        jobs = [
            {
                # Issuers outside the US get a CINS, a CUSIP starting with a letter.
                "idType": "ID_CINS" if c[:1].isalpha() else "ID_CUSIP",
                "idValue": c,
                **({"exchCode": "US"} if us_only else {}),
            }
            for c in batch
        ]
        response = None
        for _attempt in range(3):
            try:
                response = await client.post(
                    _OPENFIGI_URL, json=jobs, headers=headers, timeout=30
                )
            except httpx.RequestError as exc:
                logger.warning("[13f] OpenFIGI request failed: %r", exc)
                return found or None
            if response.status_code != 429:
                break
            wait = int(response.headers.get("ratelimit-reset", "60") or 60)
            logger.info("[13f] OpenFIGI rate limit, waiting %ss", wait)
            await asyncio.sleep(min(max(wait, 1), 60))
        if response is None or response.status_code != 200:
            logger.warning(
                "[13f] OpenFIGI returned status=%s",
                response.status_code if response is not None else None,
            )
            return found or None
        for cusip, result in zip(batch, response.json()):
            data = [
                d
                for d in (result or {}).get("data") or []
                if us_only or d.get("marketSector") == "Equity"
            ]
            first = data[0] if data else {}
            found[cusip] = {"ticker": first.get("ticker"), "name": first.get("name")}
        remaining = response.headers.get("ratelimit-remaining")
        if remaining is not None and remaining.isdigit() and int(remaining) == 0:
            await asyncio.sleep(
                min(int(response.headers.get("ratelimit-reset", "60") or 60), 60)
            )
    return found


async def openfigi_lookup(
    client: httpx.AsyncClient, cusips: list[str]
) -> dict[str, dict]:
    """Ask OpenFIGI for the ticker of each CUSIP.

    Tries the US composite listing first, then any equity listing for what is
    left (some foreign issuers' US shares only map that way). Sends 10 CUSIPs
    per request (100 with ``OPENFIGI_API_KEY``) and waits out the rate limit.
    A CUSIP OpenFIGI doesn't know maps to ``{"ticker": None}`` so a cache can
    skip it next time; one OpenFIGI couldn't be asked about is left out.
    """
    found = await _figi_pass(client, cusips, us_only=True) or {}
    missing = [c for c in cusips if c in found and not found[c]["ticker"]]
    if missing:
        retry = await _figi_pass(client, missing, us_only=False) or {}
        found.update({c: v for c, v in retry.items() if v["ticker"]})
    return found


def make_cusip_mapper(client: httpx.AsyncClient, repo) -> CusipMapper:
    """A :data:`CusipMapper` that asks OpenFIGI only for CUSIPs ``repo`` lacks.

    :param repo: a ``CusipTickerRepo`` (``get_many`` / ``upsert_many``).
    """

    async def mapper(cusips: list[str]) -> dict[str, dict]:
        known = await repo.get_many(cusips)
        unknown = [c for c in cusips if c not in known]
        found = await openfigi_lookup(client, unknown) if unknown else {}
        await repo.upsert_many(found)
        return {**known, **found}

    return mapper
