"""Background worker that files each index's breadth under its NYSE session.

The scanner behind ``market_breadth_service`` only knows today's state, so
storing one row per session is what gives the breadth chart its history. Each
pass overwrites the current session's row, so the row left behind holds that
session's closing figures.
"""

import asyncio
import logging

from ..infra.repos import MarketBreadthRepo
from ..services.market_breadth_service import get_market_breadth

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL = 1800  # 30 minutes
DEFAULT_RETENTION_DAYS = 730
_MIN_BACKOFF = 30
_MAX_BACKOFF = 900


async def capture_breadth(repo: MarketBreadthRepo) -> list[dict]:
    """Fetch breadth and store one row per index for the current session.

    :return: The stored rows; empty when the scanner or the calendar failed.
    """
    data = await get_market_breadth()
    if data is None or not data.get("session_date"):
        return []
    stored = []
    for universe in data["universes"]:
        stored.append(
            await repo.upsert_session(
                universe["key"],
                data["session_date"],
                {
                    **universe,
                    "benchmark_change_pct": universe["benchmark"]["change_pct"],
                },
            )
        )
    return stored


async def run_market_breadth_snapshots(
    repo: MarketBreadthRepo,
    interval: int = DEFAULT_INTERVAL,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> None:
    """Capture breadth every ``interval`` seconds.

    :param repo: Where snapshots are stored.
    :param interval: Seconds between passes.
    :param retention_days: Sessions older than this are pruned.
    """
    backoff = _MIN_BACKOFF
    while True:
        try:
            stored = await capture_breadth(repo)
            if stored:
                logger.info(
                    "[market-breadth] %s: %s",
                    stored[0]["session_date"],
                    ", ".join(
                        f"{row['universe']} {row['pct_above_sma200']}% > 200d"
                        for row in stored
                    ),
                )
                await repo.prune(keep_days=retention_days)
            else:
                logger.debug("[market-breadth] nothing captured this pass")
            backoff = _MIN_BACKOFF
            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            logger.error("[market-breadth] error: %r — retrying in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)
