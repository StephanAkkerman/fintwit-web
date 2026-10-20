"""IBKR Gateway client using ib_insync.

Connects to a running IB Gateway container (read-only) and exposes
positions, today's trade executions, and account summary values.

Architecture note
-----------------
ib_insync binds its Futures to whichever asyncio loop is current when IB()
is constructed.  If constructed inside uvicorn's running loop, its internal
Futures are bound to uvicorn's loop, which makes bridging impossible.

Fix: create IB() *inside* a dedicated daemon thread that owns its own loop.
All ib_insync coroutines are wrapped in private ``_*_on_ib_loop()`` methods
that run entirely on that loop via ``asyncio.run_coroutine_threadsafe()``.
The result is bridged back to uvicorn's loop with ``asyncio.wrap_future()``.

Configuration (env vars):
  IBKR_HOST       hostname of the IB Gateway container  (default: ibgateway)
    IBKR_PORT       IB API port.
                                    For ghcr.io/gnzsnz/ib-gateway in Docker network: 4003 live, 4004 paper.
                                    For direct/non-socat setups: often 4001 live, 4002 paper. (default: 4001)
  IBKR_CLIENT_ID  client slot number                     (default: 1)
    IBKR_CONNECT_TIMEOUT  connect timeout in seconds       (default: 30)
"""

import asyncio
import logging
import math
import os
import sys
import threading
from datetime import datetime, timezone

from ib_insync import IB

logger = logging.getLogger(__name__)
# The gateway needs a manual (2FA) login after every restart and weekly reset.
# docker-compose.yml publishes its VNC server on host port 5901.
LOGIN_HINT = (
    "restart the ibgateway container and approve the IBKR 2FA prompt, or log in "
    "via VNC on port 5901"
)

_MAX_FLOAT = sys.float_info.max
_ACCOUNT_TAGS = (
    "NetLiquidation,TotalCashValue,UnrealizedPnL,RealizedPnL,GrossPositionValue"
)


def default_ibkr_port(host: str, trading_mode: str | None = None) -> int:
    """API port for ``host`` when ``IBKR_PORT`` isn't set.

    The ``ibgateway`` compose service (ghcr.io/gnzsnz/ib-gateway) relays the API
    to other containers on 4003 (live) / 4004 (paper). Anything else is a native
    IB Gateway or compose's host-side mapping, both on 4001 / 4002.
    """
    mode = trading_mode if trading_mode is not None else os.getenv("TRADING_MODE")
    paper = (mode or "live").strip().lower() == "paper"
    if host == "ibgateway":
        return 4004 if paper else 4003
    return 4002 if paper else 4001


def _finite(value) -> float | None:
    """``value`` as a float, or ``None`` for IB's unset/NaN sentinels."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number) or abs(number) >= _MAX_FLOAT:
        return None
    return number


def position_row(position, mark=None) -> dict:
    """Flatten an ib_insync ``Position`` (and its ``PortfolioItem``) into a row.

    :param position: ``ib_insync.Position``.
    :param mark: Matching ``ib_insync.PortfolioItem``, when TWS has pushed one.
    """
    # Portfolio contracts come back fully qualified (primary exchange, local
    # symbol); bare positions sometimes don't.
    contract = mark.contract if mark else position.contract
    multiplier = _finite(contract.multiplier) if contract.multiplier else None
    return {
        "account": position.account,
        "symbol": contract.symbol,
        "sec_type": contract.secType,
        "exchange": position.contract.exchange or contract.primaryExchange or "",
        "primary_exchange": contract.primaryExchange or None,
        "currency": contract.currency,
        "con_id": contract.conId or None,
        "local_symbol": contract.localSymbol or None,
        "expiry": contract.lastTradeDateOrContractMonth or None,
        "strike": _finite(contract.strike) if contract.strike else None,
        "right": contract.right or None,
        "multiplier": multiplier,
        "quantity": float(position.position),
        "avg_cost": float(position.avgCost),
        "market_price": _finite(mark.marketPrice) if mark else None,
        "market_value": _finite(mark.marketValue) if mark else None,
        "unrealized_pnl": _finite(mark.unrealizedPNL) if mark else None,
    }


#: Yahoo Finance suffix for each non-US IBKR exchange code. US venues (SMART,
#: NASDAQ, NYSE, ARCA, ...) need no suffix and are simply absent.
_YAHOO_SUFFIXES = {
    "LSE": ".L",
    "LSEETF": ".L",
    "AEB": ".AS",
    "IBIS": ".DE",
    "IBIS2": ".DE",
    "FWB": ".F",
    "SBF": ".PA",
    "EBS": ".SW",
    "BVME": ".MI",
    "BM": ".MC",
    "ENEXT.BE": ".BR",
    "SFB": ".ST",
    "CPH": ".CO",
    "OSE": ".OL",
    "TSE": ".TO",
    "VENTURE": ".V",
    "SEHK": ".HK",
    "ASX": ".AX",
    "TSEJ": ".T",
}


def quote_symbol(row: dict) -> str | None:
    """Yahoo symbol to price an IBKR position with, or ``None`` if Yahoo can't.

    A bare ``ARKG`` on Yahoo is the US ETF; the LSE listing IBKR holds is
    ``ARKG.L``. Derivatives have no single Yahoo quote, so they rely on IBKR's
    own mark only.
    """
    if row.get("sec_type") != "STK":
        return None
    symbol = str(row.get("symbol") or "").strip().upper().replace(" ", "-")
    if not symbol:
        return None
    for venue in (row.get("primary_exchange"), row.get("exchange")):
        suffix = _YAHOO_SUFFIXES.get(str(venue or "").upper())
        if suffix:
            return symbol + suffix
    return symbol


def ibkr_contract_label(row: dict) -> str:
    """Readable contract name, e.g. ``DRAM 2026-12-18 100 C`` for an option."""
    symbol = str(row.get("symbol") or "")
    if row.get("sec_type") not in ("OPT", "FOP", "FUT"):
        return symbol
    parts = [symbol]
    expiry = str(row.get("expiry") or "")
    if len(expiry) == 8 and expiry.isdigit():
        expiry = f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:]}"
    if expiry:
        parts.append(expiry)
    strike = row.get("strike")
    if strike:
        parts.append(f"{float(strike):g}")
    if row.get("right"):
        parts.append(str(row["right"])[0])
    return " ".join(parts)


class IbkrGateway:
    """Persistent, read-only connection to the IB Gateway."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
    ) -> None:
        self._host = host or os.getenv("IBKR_HOST", "ibgateway")
        self._port = port or int(
            os.getenv("IBKR_PORT") or default_ibkr_port(self._host)
        )
        self._client_id = client_id or int(os.getenv("IBKR_CLIENT_ID", "1"))
        self._connect_timeout = float(os.getenv("IBKR_CONNECT_TIMEOUT", "30"))
        self.last_sync: datetime | None = None
        self.last_error: str | None = None
        self._connect_lock = asyncio.Lock()

        self._ib: IB | None = None
        self._ib_loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="ibkr-loop"
        )
        self._thread.start()
        # Wait for IB() to be constructed on the thread before returning
        if not self._ready.wait(timeout=5):
            raise RuntimeError("[ibkr] background loop failed to start")

    # ------------------------------------------------------------------
    # Internal: dedicated loop
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Entry point for the ib_insync daemon thread.

        IB() must be created here so it captures *this* loop, not uvicorn's.
        """
        asyncio.set_event_loop(self._ib_loop)
        self._ib = IB()
        self._ready.set()
        self._ib_loop.run_forever()

    def _submit(self, coro) -> asyncio.Future:
        """Schedule a raw coroutine on the ib_insync loop.

        Returns an asyncio.Future bound to the *caller's* loop (uvicorn's),
        so it can be awaited normally from any async context.
        """
        concurrent_fut = asyncio.run_coroutine_threadsafe(coro, self._ib_loop)
        return asyncio.wrap_future(concurrent_fut)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        async with self._connect_lock:
            if self._ib is not None and self._ib.isConnected():
                return True

            try:
                logger.info(
                    "[ibkr] connecting to %s:%d (client %d, timeout=%.1fs)",
                    self._host,
                    self._port,
                    self._client_id,
                    self._connect_timeout,
                )
                await self._submit(self._connect_on_ib_loop())
                logger.info(
                    "[ibkr] connected to %s:%d (client %d)",
                    self._host,
                    self._port,
                    self._client_id,
                )
                self.last_error = None
                return True
            except ConnectionRefusedError:
                self.last_error = f"Connection refused — {LOGIN_HINT}"
                logger.warning(
                    "[ibkr] connection refused on %s:%d — " + LOGIN_HINT,
                    self._host,
                    self._port,
                )
                return False
            except TimeoutError as exc:
                self.last_error = (
                    f"Connect timeout after {self._connect_timeout:.1f}s; IB Gateway "
                    f"is not logged in — {LOGIN_HINT}"
                )
                logger.error(
                    "[ibkr] connect timed out after %.1fs: %r — " + LOGIN_HINT,
                    self._connect_timeout,
                    exc,
                )
                return False
            except Exception as exc:
                self.last_error = str(exc)
                logger.error("[ibkr] connect failed: %r", exc)
                return False

    async def _connect_on_ib_loop(self) -> None:
        """Runs entirely on the ib_insync loop — all internal Futures stay there."""
        await self._ib.connectAsync(
            self._host,
            self._port,
            clientId=self._client_id,
            readonly=True,
            timeout=self._connect_timeout,
        )
        # Brief pause so the server can push initial position/account data
        await asyncio.sleep(1)

    async def _ensure_connected(self) -> bool:
        if self._ib is not None and self._ib.isConnected():
            return True
        return await self.connect()

    @property
    def address(self) -> str:
        """``host:port`` the gateway connects to."""
        return f"{self._host}:{self._port}"

    def is_connected(self) -> bool:
        return self._ib is not None and self._ib.isConnected()

    def disconnect(self) -> None:
        if self._ib and self._ib.isConnected():
            self._ib_loop.call_soon_threadsafe(self._ib.disconnect)

    def stop(self) -> None:
        """Disconnect and shut down the background loop."""
        self.disconnect()
        self._ib_loop.call_soon_threadsafe(self._ib_loop.stop)

    # ------------------------------------------------------------------
    # Data fetchers
    # ------------------------------------------------------------------

    async def get_positions(self) -> list[dict]:
        """Return all non-zero positions for all accounts.

        Each row carries IBKR's own mark (``market_price``, ``market_value``,
        ``unrealized_pnl``) from the portfolio updates TWS pushes, so the
        dashboard shows the same numbers as the IBKR app, plus enough contract
        detail to tell an option or a foreign listing apart from a US stock.
        """
        if not await self._ensure_connected():
            return []
        # positions()/portfolio() read ib_insync's in-memory cache — safe from any thread
        marks = {
            (item.account, item.contract.conId): item for item in self._ib.portfolio()
        }
        return [
            position_row(p, marks.get((p.account, p.contract.conId)))
            for p in self._ib.positions()
            if float(p.position) != 0
        ]

    async def get_executions(self) -> list[dict]:
        """Return today's trade executions (fills)."""
        if not await self._ensure_connected():
            return []
        try:
            return await self._submit(self._executions_on_ib_loop())
        except Exception as exc:
            logger.error("[ibkr] reqExecutions failed: %r", exc)
            return []

    async def _executions_on_ib_loop(self) -> list[dict]:
        fills = await self._ib.reqExecutionsAsync()
        result = []
        for f in fills:
            commission: float | None = None
            if (
                f.commissionReport
                and f.commissionReport.commission < _MAX_FLOAT
                and f.commissionReport.commission >= 0
            ):
                commission = float(f.commissionReport.commission)

            executed_at: datetime | None = None
            if f.time:
                executed_at = (
                    f.time.astimezone(timezone.utc)
                    if f.time.tzinfo
                    else f.time.replace(tzinfo=timezone.utc)
                )

            result.append(
                {
                    "exec_id": f.execution.execId,
                    "account": f.execution.acctNumber,
                    "symbol": f.contract.symbol,
                    "sec_type": f.contract.secType,
                    "currency": f.contract.currency,
                    "side": f.execution.side,  # BOT / SLD
                    "quantity": float(f.execution.shares),
                    "price": float(f.execution.price),
                    "commission": commission,
                    "executed_at": executed_at,
                }
            )
        return result

    async def get_account_summary(self) -> dict:
        """Return key account values (NLV, cash, P&L, etc.)."""
        if not await self._ensure_connected():
            return {}
        try:
            return await self._submit(self._account_summary_on_ib_loop())
        except Exception as exc:
            logger.error("[ibkr] reqAccountSummary failed: %r", exc)
            return {}

    async def _account_summary_on_ib_loop(self) -> dict:
        # accountValues() returns the values that TWS pushes automatically
        # after connecting — no persistent subscription needed, and no risk
        # of hitting the "maximum account summary requests" limit.
        tags = set(_ACCOUNT_TAGS.split(","))
        result: dict[str, dict] = {}
        for av in self._ib.accountValues():
            if av.tag in tags and av.currency not in ("BASE", ""):
                try:
                    result[av.tag] = {
                        "value": float(av.value),
                        "currency": av.currency,
                    }
                except ValueError:
                    pass
        return result
