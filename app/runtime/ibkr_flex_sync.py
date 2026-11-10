"""Background worker that pulls the IBKR Flex statement every few hours.

It fills in what the Gateway sync misses while the Gateway is logged out:
trades (deduplicated with the Gateway's own by execution id), daily account
value and cash, and, when the Gateway has nothing newer, positions.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone

from ..infra.repos import IbkrRepo
from ..services.ibkr import IbkrGateway
from ..services.ibkr_flex import close_of, fetch_statement, parse_statement

logger = logging.getLogger(__name__)

_RETRY_AFTER = 900


@dataclass
class FlexSyncState:
    """What ``/api/ibkr/status`` reports about the Flex sync."""

    interval: int
    last_sync: datetime | None = None
    last_error: str | None = None
    statement_date: date | None = None

    def as_dict(self) -> dict:
        return {
            "configured": True,
            "interval": self.interval,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "last_error": self.last_error,
            "statement_date": (
                self.statement_date.isoformat() if self.statement_date else None
            ),
        }


async def sync_flex_once(
    repo: IbkrRepo,
    xml_text: str,
    gateway: IbkrGateway | None = None,
) -> dict:
    """Store one Flex statement and return what was written.

    Positions are only replaced when the Gateway is not syncing and the
    stored positions are older than the statement's close.
    """
    counts = {"trades": 0, "equity_days": 0, "positions": 0, "statement_date": None}
    for statement in parse_statement(xml_text):
        to_date = statement["to_date"]
        if to_date and (
            counts["statement_date"] is None or to_date > counts["statement_date"]
        ):
            counts["statement_date"] = to_date
        counts["trades"] += await repo.upsert_trades(statement["trades"])
        counts["equity_days"] += await repo.upsert_equity(statement["equity"])

        positions = statement["positions"]
        if positions is None or to_date is None:
            continue
        marks_at = min(close_of(to_date), datetime.now(timezone.utc))
        if gateway is not None and gateway.state() == "ok":
            continue
        stored_at = await repo.latest_position_sync(statement["account"])
        if stored_at is not None and stored_at >= marks_at:
            continue
        await repo.sync_positions(statement["account"], positions, synced_at=marks_at)
        counts["positions"] += len(positions)
    return counts


async def run_ibkr_flex_sync(
    repo: IbkrRepo,
    token: str,
    query_id: str,
    state: FlexSyncState,
    gateway: IbkrGateway | None = None,
) -> None:
    """Fetch and store the Flex statement every ``state.interval`` seconds."""
    while True:
        delay = state.interval
        try:
            xml_text = await fetch_statement(token, query_id)
            counts = await sync_flex_once(repo, xml_text, gateway)
            state.statement_date = counts["statement_date"]
            state.last_sync = datetime.now(timezone.utc)
            state.last_error = None
            logger.info(
                "[ibkr-flex] statement to %s: %d trade(s), %d day(s) of equity, "
                "%d position(s) written",
                state.statement_date,
                counts["trades"],
                counts["equity_days"],
                counts["positions"],
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            repeated = state.last_error == str(exc)
            state.last_error = str(exc)
            logger.log(
                logging.DEBUG if repeated else logging.ERROR,
                "[ibkr-flex] error: %r; retrying in %ds",
                exc,
                _RETRY_AFTER,
            )
            delay = min(_RETRY_AFTER, state.interval)
        await asyncio.sleep(delay)
