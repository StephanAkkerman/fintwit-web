"""IBKR Flex Web Service client: positions, trades and cash without a Gateway.

An Activity Flex Query is a statement the owner defines once in the IBKR
portal (Performance & Reports > Flex Queries). The Flex Web Service hands it
out over plain HTTPS with a long-lived token, so it keeps working while the
IB Gateway sits logged out after the weekly 2FA reset. Its data is as of the
last statement IBKR generated (normally the previous close), so the Gateway
stays the source while it is syncing.

Configuration (env vars):
  IBKR_FLEX_TOKEN     Flex Web Service token (Settings > Flex Web Service)
  IBKR_FLEX_QUERY_ID  id of the Activity Flex Query to fetch
  IBKR_FLEX_INTERVAL  seconds between fetches (default 21600, six hours)

The query needs the Open Positions, Trades (execution level, with the IB
Execution ID), Cash Report and, optionally, Net Asset Value (NAV) in Base
sections, delivered as XML.
"""

import asyncio
import logging
import math
import os
import re
from datetime import date, datetime, time, timezone
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

FLEX_BASE_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"
# IBKR rejects requests that carry no User-Agent.
_HEADERS = {"User-Agent": "fintwit-web/1.0"}
_TIMEOUT = httpx.Timeout(60.0, connect=15.0)
# "Statement generation in progress" and "please try again shortly".
_RETRY_CODES = {"1001", "1004", "1009", "1019", "1021"}
_POLL_DELAY = 5.0
_POLL_ATTEMPTS = 12
# Flex reports times in US Eastern unless the query says otherwise.
_EASTERN = ZoneInfo("America/New_York")
_MARKET_CLOSE = time(16, 0)


class FlexError(RuntimeError):
    """The Flex Web Service refused the request or returned no statement."""


def flex_credentials() -> tuple[str, str] | None:
    """Return ``(token, query_id)`` when both env vars are set."""
    token = os.getenv("IBKR_FLEX_TOKEN", "").strip()
    query_id = os.getenv("IBKR_FLEX_QUERY_ID", "").strip()
    if token and query_id:
        return token, query_id
    return None


# ----------------------------------------------------------------------
# Fetching
# ----------------------------------------------------------------------


def _response_status(xml_text: str) -> tuple[str, str, str, ElementTree.Element]:
    """Return ``(status, error_code, error_message, root)`` of a service reply."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise FlexError(f"Flex reply is not XML: {xml_text[:200]!r}") from exc
    return (
        (root.findtext("Status") or "").strip(),
        (root.findtext("ErrorCode") or "").strip(),
        (root.findtext("ErrorMessage") or "").strip(),
        root,
    )


async def fetch_statement(
    token: str,
    query_id: str,
    *,
    client: httpx.AsyncClient | None = None,
    poll_delay: float = _POLL_DELAY,
    attempts: int = _POLL_ATTEMPTS,
) -> str:
    """Run the Flex Query and return the statement XML.

    :param token: Flex Web Service token.
    :param query_id: Activity Flex Query id.
    :param client: Optional client (tests pass one with a mock transport).
    :param poll_delay: Seconds between polls while IBKR builds the statement.
    :param attempts: Polls before giving up.
    :raises FlexError: When IBKR answers with an error.
    """
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS)
    try:
        reply = await client.get(
            f"{FLEX_BASE_URL}/SendRequest",
            params={"t": token, "q": query_id, "v": "3"},
        )
        reply.raise_for_status()
        status, code, message, root = _response_status(reply.text)
        if status != "Success":
            raise FlexError(f"SendRequest failed ({code}): {message or status}")
        reference = (root.findtext("ReferenceCode") or "").strip()
        url = (root.findtext("Url") or "").strip() or f"{FLEX_BASE_URL}/GetStatement"
        if not reference:
            raise FlexError("SendRequest returned no reference code")

        for attempt in range(attempts):
            reply = await client.get(url, params={"t": token, "q": reference, "v": "3"})
            reply.raise_for_status()
            if "<FlexQueryResponse" in reply.text[:500]:
                return reply.text
            status, code, message, _ = _response_status(reply.text)
            if code not in _RETRY_CODES:
                raise FlexError(f"GetStatement failed ({code}): {message or status}")
            if attempt + 1 < attempts:
                await asyncio.sleep(poll_delay)
        raise FlexError("Statement was still being generated; try again later")
    finally:
        if own_client:
            await client.aclose()


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------


def _float(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _int(value: str | None) -> int | None:
    number = _float(value)
    return int(number) if number is not None else None


def parse_flex_date(value: str | None) -> date | None:
    """Parse a Flex date in any of its formats (``20261107``, ``2026-11-07``)."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) < 8:
        return None
    try:
        return datetime.strptime(digits[:8], "%Y%m%d").date()
    except ValueError:
        return None


def parse_flex_datetime(value: str | None) -> datetime | None:
    """Parse a Flex date-time (``20261107;153012``) as Eastern time, to UTC."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) < 8:
        return None
    try:
        if len(digits) >= 14:
            local = datetime.strptime(digits[:14], "%Y%m%d%H%M%S")
        else:
            local = datetime.strptime(digits[:8], "%Y%m%d")
    except ValueError:
        return None
    return local.replace(tzinfo=_EASTERN).astimezone(timezone.utc)


def close_of(day: date) -> datetime:
    """The US close on ``day``, in UTC: when a statement's marks were taken."""
    return datetime.combine(day, _MARKET_CLOSE, tzinfo=_EASTERN).astimezone(
        timezone.utc
    )


def _symbol(el: ElementTree.Element) -> tuple[str, str | None]:
    """Return ``(symbol, local_symbol)`` the way TWS names the contract.

    TWS calls an option by its underlying (``AAPL``) with the OCC code as the
    local symbol; Flex puts the OCC code in ``symbol``.
    """
    symbol = (el.get("symbol") or "").strip()
    underlying = (el.get("underlyingSymbol") or "").strip()
    if underlying and el.get("assetCategory") in ("OPT", "FOP", "FUT", "WAR"):
        return underlying, symbol or None
    return symbol, None


def _is_detail(el: ElementTree.Element, level: str) -> bool:
    detail = el.get("levelOfDetail")
    return detail is None or detail.upper() == level


def _position_row(el: ElementTree.Element, account: str) -> dict | None:
    quantity = _float(el.get("position"))
    symbol, local_symbol = _symbol(el)
    if not symbol or not quantity:
        return None
    multiplier = _float(el.get("multiplier"))
    cost_price = _float(el.get("costBasisPrice")) or 0.0
    sec_type = el.get("assetCategory") or "STK"
    # TWS reports avg cost per contract (price x multiplier); match it so
    # cost basis is quantity x avg_cost for every source.
    avg_cost = cost_price * (multiplier or 1.0) if sec_type != "STK" else cost_price
    expiry = parse_flex_date(el.get("expiry"))
    exchange = el.get("listingExchange") or None
    return {
        "account": el.get("accountId") or account,
        "symbol": symbol,
        "sec_type": sec_type,
        "exchange": exchange or "",
        "primary_exchange": exchange,
        "currency": el.get("currency") or "USD",
        "con_id": _int(el.get("conid")),
        "local_symbol": local_symbol,
        "expiry": expiry.strftime("%Y%m%d") if expiry else None,
        "strike": _float(el.get("strike")) or None,
        "right": (el.get("putCall") or "").strip() or None,
        "multiplier": multiplier,
        "quantity": quantity,
        "avg_cost": avg_cost,
        "market_price": _float(el.get("markPrice")),
        "market_value": _float(el.get("positionValue")),
        "unrealized_pnl": _float(el.get("fifoPnlUnrealized")),
    }


def _trade_row(el: ElementTree.Element, account: str) -> dict | None:
    exec_id = (el.get("ibExecID") or "").strip()
    symbol, _ = _symbol(el)
    quantity = _float(el.get("quantity"))
    price = _float(el.get("tradePrice"))
    if not exec_id or not symbol or not quantity or price is None:
        return None
    side = (el.get("buySell") or "").upper()
    if side.startswith("BUY"):
        side = "BOT"
    elif side.startswith("SELL"):
        side = "SLD"
    else:
        side = "BOT" if quantity > 0 else "SLD"
    commission = _float(el.get("ibCommission"))
    return {
        "exec_id": exec_id,
        "account": el.get("accountId") or account,
        "symbol": symbol,
        "sec_type": el.get("assetCategory") or "STK",
        "currency": el.get("currency") or "USD",
        "side": side,
        "quantity": abs(quantity),
        "price": price,
        "commission": abs(commission) if commission is not None else None,
        "executed_at": parse_flex_datetime(el.get("dateTime") or el.get("tradeDate")),
    }


def _equity_rows(statement: ElementTree.Element, account: str) -> list[dict]:
    rows = []
    for el in statement.iter("EquitySummaryByReportDateInBase"):
        day = parse_flex_date(el.get("reportDate"))
        total = _float(el.get("total"))
        if day is None or total is None:
            continue
        stock = _float(el.get("stock"))
        options = _float(el.get("options"))
        rows.append(
            {
                "account": el.get("accountId") or account,
                "report_date": day.isoformat(),
                "currency": el.get("currency") or None,
                "cash": _float(el.get("cash")),
                "stock": stock,
                "options": options,
                "total": total,
            }
        )
    return rows


def _ending_cash(statement: ElementTree.Element) -> float | None:
    """Cash at the end of the statement, in base currency."""
    for el in statement.iter("CashReportCurrency"):
        if (
            el.get("currency") == "BASE_SUMMARY"
            or (el.get("levelOfDetail") or "").lower() == "basecurrency"
        ):
            return _float(el.get("endingCash"))
    return None


def parse_statement(xml_text: str) -> list[dict]:
    """Turn Flex statement XML into one dict per account.

    Each dict has ``account``, ``to_date`` (a ``date``), ``positions``
    (``None`` without an Open Positions section), ``trades`` and ``equity``
    (daily NAV rows, newest last). ``positions`` and ``trades`` match the
    rows the Gateway sync writes.
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise FlexError("Flex statement is not valid XML") from exc

    statements = []
    for statement in root.iter("FlexStatement"):
        account = statement.get("accountId") or ""
        to_date = parse_flex_date(statement.get("toDate"))

        # None when the query has no Open Positions section, so a missing
        # section is never mistaken for an empty account.
        positions = (
            [
                row
                for el in statement.iter("OpenPosition")
                if _is_detail(el, "SUMMARY") and (row := _position_row(el, account))
            ]
            if statement.find("OpenPositions") is not None
            else None
        )
        trades = [
            row
            for el in statement.iter("Trade")
            if _is_detail(el, "EXECUTION") and (row := _trade_row(el, account))
        ]
        equity = sorted(
            _equity_rows(statement, account), key=lambda r: r["report_date"]
        )

        base_currency = next(
            (r["currency"] for r in reversed(equity) if r["currency"]), None
        )
        info = next(statement.iter("AccountInformation"), None)
        if base_currency is None and info is not None:
            base_currency = info.get("currency") or None

        # Without the NAV section, the Cash Report still gives the end cash.
        cash = _ending_cash(statement)
        if to_date is not None and cash is not None:
            day = to_date.isoformat()
            last = equity[-1] if equity else None
            if last is None or last["report_date"] != day:
                equity.append(
                    {
                        "account": account,
                        "report_date": day,
                        "currency": base_currency,
                        "cash": cash,
                        "stock": None,
                        "options": None,
                        "total": None,
                    }
                )
            elif last["cash"] is None:
                last["cash"] = cash
        for row in equity:
            row["currency"] = row["currency"] or base_currency

        statements.append(
            {
                "account": account,
                "to_date": to_date,
                "positions": positions,
                "trades": trades,
                "equity": equity,
            }
        )
    if not statements:
        raise FlexError("Flex reply holds no statement")
    return statements


def flex_account_summary(equity_rows: list[dict]) -> dict:
    """Shape the newest Flex day per account like the Gateway's summary.

    Values are summed over accounts that share a base currency (the first
    account's currency wins otherwise). Each value says which day it is from.
    """
    if not equity_rows:
        return {}
    currency = next((r["currency"] for r in equity_rows if r["currency"]), None)
    rows = [r for r in equity_rows if r["currency"] in (currency, None)]
    as_of = max(r["report_date"] for r in rows)

    def total(*fields: str) -> float | None:
        values = [r[f] for r in rows for f in fields if r.get(f) is not None]
        return sum(values) if values else None

    tags = {
        "NetLiquidation": total("total"),
        "TotalCashValue": total("cash"),
        "GrossPositionValue": total("stock", "options"),
    }
    return {
        tag: {
            "value": value,
            "currency": currency or "",
            "as_of": as_of,
            "source": "flex",
        }
        for tag, value in tags.items()
        if value is not None
    }
