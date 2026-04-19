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
import os
import sys
import threading
from datetime import datetime, timezone

from ib_insync import IB

logger = logging.getLogger(__name__)

_MAX_FLOAT = sys.float_info.max
_ACCOUNT_TAGS = (
    "NetLiquidation,TotalCashValue,UnrealizedPnL,RealizedPnL,GrossPositionValue"
)


class IbkrGateway:
    """Persistent, read-only connection to the IB Gateway."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
    ) -> None:
        self._host = host or os.getenv("IBKR_HOST", "ibgateway")
        self._port = port or int(os.getenv("IBKR_PORT", "4001"))
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
                self.last_error = "Connection refused — log in to IB Gateway via VNC at localhost:5900"
                logger.warning(
                    "[ibkr] connection refused on %s:%d — "
                    "log in to IB Gateway first via VNC at localhost:5900",
                    self._host,
                    self._port,
                )
                return False
            except TimeoutError as exc:
                self.last_error = (
                    f"Connect timeout after {self._connect_timeout:.1f}s "
                    "(gateway not ready/auth pending)"
                )
                logger.error(
                    "[ibkr] connect timed out after %.1fs: %r",
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
        """Return all non-zero positions for all accounts."""
        if not await self._ensure_connected():
            return []
        # positions() reads ib_insync's in-memory cache — safe from any thread
        return [
            {
                "account": p.account,
                "symbol": p.contract.symbol,
                "sec_type": p.contract.secType,
                "exchange": p.contract.exchange or "",
                "currency": p.contract.currency,
                "quantity": float(p.position),
                "avg_cost": float(p.avgCost),
            }
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
