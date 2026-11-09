"""Background worker that runs the stage-2 breakout screener.

Weekly bars barely move within a day, so the screen runs every few hours
(default 6) rather than continuously: a pass evaluates a few hundred symbols
on Yahoo, which is where the cost is. Each pass also refreshes the latest
close of breakouts flagged in the last few months that the screen no longer
lists, so the track record on the dashboard keeps counting after a name drops
out of the screen.
"""

import asyncio
import logging

from ..infra.repos import BreakoutRepo
from ..services.breakout_screener import run_screen
from ..services.price_history_service import get_price_series

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL = 6 * 3600
#: Flagged breakouts whose return keeps being tracked.
TRACK_DAYS = 180
_MIN_BACKOFF = 300
_MAX_BACKOFF = 3600


async def refresh_track_record(repo: BreakoutRepo, listed: set[str]) -> int:
    """Update the last close of flagged breakouts the latest run didn't list."""
    symbols = {r["symbol"] for r in await repo.flagged(days=TRACK_DAYS)} - listed
    updated = 0
    for symbol in sorted(symbols):
        series = await get_price_series(symbol, "1M")
        if series:
            updated += await repo.update_last_close(symbol, series[-1]["close"])
    return updated


async def screen_once(repo: BreakoutRepo) -> dict | None:
    """Run the screen, store it and refresh the track record."""
    screen = await run_screen()
    if screen is None:
        return None
    run = await repo.record_run(screen)
    listed = {r["symbol"] for r in screen["breakouts"] + screen["watch"]}
    await refresh_track_record(repo, listed)
    return run


async def run_breakout_screens(
    repo: BreakoutRepo, interval: int = DEFAULT_INTERVAL
) -> None:
    """Screen for breakouts every ``interval`` seconds, starting now."""
    backoff = _MIN_BACKOFF
    while True:
        try:
            run = await screen_once(repo)
            if run is None:
                logger.warning(
                    "[breakouts] screen failed (scanner or SPY history), retry in %ds",
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF)
                continue
            logger.info(
                "[breakouts] week of %s: %d breakouts, %d on watch (%d of %d evaluated)",
                run["as_of"],
                run["breakouts"],
                run["watch"],
                run["evaluated"],
                run["universe"],
            )
            await repo.prune()
            backoff = _MIN_BACKOFF
            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            logger.error("[breakouts] error: %r, retrying in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)
