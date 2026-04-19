"""Background worker that periodically syncs IBKR positions and trades.

Runs as an asyncio task started during FastAPI lifespan.
Reconnects automatically on transient errors with exponential backoff.
"""

import asyncio
import logging
from datetime import datetime, timezone

from ..infra.repos import IbkrRepo
from ..services.ibkr import IbkrGateway

logger = logging.getLogger(__name__)

_MIN_BACKOFF = 10
_MAX_BACKOFF = 300


async def run_ibkr_sync(
    repo: IbkrRepo,
    gateway: IbkrGateway,
    interval: int = 60,
) -> None:
    """Sync positions and today's executions from IBKR on a fixed interval.

    :param repo: IbkrRepo instance for DB persistence.
    :param gateway: IbkrGateway instance managing the TWS connection.
    :param interval: Seconds between syncs (default 60).
    """
    backoff = _MIN_BACKOFF

    while True:
        try:
            connected = gateway.is_connected() or await gateway.connect()
            if not connected:
                raise RuntimeError(gateway.last_error or "IBKR connect failed")

            positions = await gateway.get_positions()

            if positions:
                accounts: dict[str, list[dict]] = {}
                for p in positions:
                    accounts.setdefault(p["account"], []).append(p)
                for account, acc_positions in accounts.items():
                    await repo.sync_positions(account, acc_positions)

            trades = await gateway.get_executions()
            if trades:
                await repo.upsert_trades(trades)

            gateway.last_sync = datetime.now(timezone.utc)
            gateway.last_error = None
            backoff = _MIN_BACKOFF

            logger.info(
                "[ibkr-sync] synced %d position(s), %d execution(s)",
                len(positions),
                len(trades),
            )
            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            gateway.disconnect()
            raise

        except Exception as exc:
            gateway.last_error = str(exc)
            logger.error("[ibkr-sync] error: %r — retrying in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)
