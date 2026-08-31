"""Background worker that records the portfolio's value on a fixed interval.

Reconstructing history from price data assumes today's quantities held all
along, which is wrong the moment a position is opened or closed. Snapshots fix
that going forward: each one is what the portfolio was actually worth at that
moment, and the history endpoint prefers them over the reconstruction.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from ..infra.repos import IbkrRepo, PortfolioRepo
from .portfolio_valuation import resolve_holdings, value_holdings

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL = 1800  # 30 minutes
_MIN_BACKOFF = 30
_MAX_BACKOFF = 900


async def capture_snapshot(
    portfolio_repo: PortfolioRepo,
    ibkr_repo: IbkrRepo,
    source: str = "auto",
) -> dict | None:
    """Value the current holdings and persist one snapshot.

    :param portfolio_repo: Repo for manual positions and snapshot storage.
    :param ibkr_repo: Repo for IBKR-synced positions.
    :param source: Holdings source to resolve (see ``resolve_holdings``).
    :return: The stored snapshot, or ``None`` when nothing is held.
    """
    resolved_source, holdings = await resolve_holdings(
        portfolio_repo, ibkr_repo, source
    )
    if not holdings:
        return None

    valuation = await value_holdings(holdings)
    totals = valuation["totals"]

    return await portfolio_repo.add_snapshot(
        {
            "source": resolved_source,
            "captured_at": datetime.now(timezone.utc),
            "market_value": totals["market_value"],
            "cost_basis": totals["cost_basis"],
            "unrealized_pnl": totals["unrealized_pnl"],
            "unrealized_pnl_percent": totals["unrealized_pnl_percent"],
            "positions": totals["positions"],
            "breakdown": [
                {
                    "symbol": position["symbol"],
                    "quantity": position["quantity"],
                    "market_price": position["market_price"],
                    "market_value": position["market_value"],
                }
                for position in valuation["positions"]
            ],
        }
    )


async def run_portfolio_snapshots(
    portfolio_repo: PortfolioRepo,
    ibkr_repo: IbkrRepo,
    interval: int = DEFAULT_INTERVAL,
    source: str = "auto",
) -> None:
    """Capture a portfolio snapshot every ``interval`` seconds.

    Skips the write when a snapshot already exists within half the interval, so
    an app restart loop cannot flood the table.

    :param portfolio_repo: Repo for manual positions and snapshot storage.
    :param ibkr_repo: Repo for IBKR-synced positions.
    :param interval: Seconds between snapshots.
    :param source: Holdings source to resolve.
    """
    backoff = _MIN_BACKOFF
    min_gap = timedelta(seconds=max(interval // 2, 60))

    while True:
        try:
            latest = await portfolio_repo.latest_snapshot()
            captured = latest.get("captured_at") if latest else None
            recent = False
            if captured:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(captured)
                recent = age < min_gap

            if not recent:
                snapshot = await capture_snapshot(portfolio_repo, ibkr_repo, source)
                if snapshot is None:
                    logger.debug("[portfolio-snapshot] no holdings to value")
                else:
                    logger.info(
                        "[portfolio-snapshot] %s value=%.2f pnl=%.2f (%d positions)",
                        snapshot["source"],
                        snapshot["market_value"],
                        snapshot["unrealized_pnl"],
                        snapshot["positions"],
                    )

            backoff = _MIN_BACKOFF
            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            logger.error(
                "[portfolio-snapshot] error: %r — retrying in %ds", exc, backoff
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)
