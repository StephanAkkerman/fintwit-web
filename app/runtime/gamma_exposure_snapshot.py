"""Background worker that records SPY's dealer gamma exposure on an interval (issue #85).

Open interest barely moves intraday, but spot does — and spot is what decides
which side of the zero-gamma flip point the market sits on. Storing a
snapshot each pass, rather than only serving a live computation, is what lets
the UI plot the positive/negative gamma regime over time instead of just its
current value.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from ..infra.repos import GammaExposureRepo
from ..services.gamma_exposure_service import DEFAULT_SYMBOL, get_gamma_exposure

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL = 1800  # 30 minutes
DEFAULT_RETENTION_DAYS = 180
_MIN_BACKOFF = 30
_MAX_BACKOFF = 900


async def capture_snapshot(
    repo: GammaExposureRepo, symbol: str = DEFAULT_SYMBOL
) -> dict | None:
    """Estimate current gamma exposure for ``symbol`` and persist one snapshot.

    :return: The stored snapshot, or ``None`` when the chain couldn't be fetched.
    """
    estimate = await get_gamma_exposure(symbol)
    if estimate is None:
        return None

    return await repo.add_snapshot(
        {
            "symbol": estimate["symbol"],
            "captured_at": datetime.now(timezone.utc),
            "spot_price": estimate["spot_price"],
            "net_gex": estimate["net_gex"],
            "call_gex": estimate["call_gex"],
            "put_gex": estimate["put_gex"],
            "flip_point": estimate["flip_point"],
            "regime": estimate["regime"],
        }
    )


async def run_gamma_exposure_snapshots(
    repo: GammaExposureRepo,
    symbol: str = DEFAULT_SYMBOL,
    interval: int = DEFAULT_INTERVAL,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> None:
    """Capture a gamma exposure snapshot every ``interval`` seconds.

    Skips the write when a snapshot already exists within half the interval,
    so an app restart loop cannot flood the table.

    :param repo: Where snapshots are stored.
    :param symbol: Underlying to track.
    :param interval: Seconds between snapshots.
    :param retention_days: Snapshots older than this are pruned.
    """
    backoff = _MIN_BACKOFF
    min_gap = timedelta(seconds=max(interval // 2, 60))

    while True:
        try:
            latest = await repo.latest_snapshot(symbol=symbol)
            captured = latest.get("captured_at") if latest else None
            recent = False
            if captured:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(captured)
                recent = age < min_gap

            if not recent:
                snapshot = await capture_snapshot(repo, symbol)
                if snapshot is None:
                    logger.debug(
                        "[gamma-exposure-snapshot] %s: could not fetch chain", symbol
                    )
                else:
                    logger.info(
                        "[gamma-exposure-snapshot] %s net_gex=%.3e regime=%s spot=%.2f",
                        snapshot["symbol"],
                        snapshot["net_gex"],
                        snapshot["regime"],
                        snapshot["spot_price"],
                    )
                    await repo.prune(symbol=symbol, keep_days=retention_days)

            backoff = _MIN_BACKOFF
            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            logger.error(
                "[gamma-exposure-snapshot] error: %r — retrying in %ds", exc, backoff
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)
