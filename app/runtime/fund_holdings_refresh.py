"""Background worker that keeps the 13F fund holdings warm.

Building them takes a few dozen SEC requests plus OpenFIGI lookups for new
CUSIPs (rate limited to 25 a minute without a key), which is too slow for a
page load. Rebuilding on a timer means the endpoint always answers from cache
and picks up new quarterly filings within ``interval``.
"""

import asyncio
import logging

import httpx

from ..infra.repos import CusipTickerRepo
from ..services.fund_holdings_service import get_fund_holdings, make_cusip_mapper

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL = 6 * 3600
_RETRY_SECONDS = 600


async def run_fund_holdings_refresh(
    client: httpx.AsyncClient,
    repo: CusipTickerRepo,
    interval: int = DEFAULT_INTERVAL,
) -> None:
    """Rebuild the fund holdings every ``interval`` seconds (sooner after a failure)."""
    mapper = make_cusip_mapper(client, repo)
    while True:
        try:
            data = await get_fund_holdings(client, mapper, refresh=True)
            if data is None:
                logger.warning("[fund-holdings] no fund's 13F could be read")
                await asyncio.sleep(_RETRY_SECONDS)
                continue
            logger.info(
                "[fund-holdings] %d funds, latest quarter %s",
                len(data["funds"]),
                data["report_date"],
            )
            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            logger.error(
                "[fund-holdings] error: %r — retrying in %ds", exc, _RETRY_SECONDS
            )
            await asyncio.sleep(_RETRY_SECONDS)
