import asyncio
import datetime
import logging
from typing import Optional

import httpx

from ..infra.repos import FundingRateRepo
from ..services.binance_service import get_funding_rates

logger = logging.getLogger(__name__)

async def run_funding_loop(repo: FundingRateRepo, client: Optional[httpx.AsyncClient] = None):
    """
    Background loop that periodically fetches Binance funding rates and updates the database.
    Runs every 4 hours, or immediately if starting up.
    """
    logger.info("Starting Binance funding rates loop...")

    should_close_client = False
    if client is None:
        client = httpx.AsyncClient()
        should_close_client = True

    try:
        while True:
            try:
                # Get the rates and time to next funding
                result = await get_funding_rates(client)

                if result:
                    all_rates, time_to_next = result

                    # Convert to DB row format
                    now = datetime.datetime.now(datetime.timezone.utc)
                    next_funding_time = now + time_to_next

                    db_rates = []
                    for item in all_rates:
                        # Extract the float
                        rate_float = float(item["lastFundingRate"])

                        db_rates.append({
                            "symbol": item["symbol"],
                            "rate": rate_float * 100, # store as percentage e.g. 0.0100
                            "next_funding_time": next_funding_time,
                            "updated_at": now
                        })

                    # Store in DB
                    if db_rates:
                        await repo.upsert_rates(db_rates)
                        logger.info(f"Updated {len(db_rates)} funding rates in database.")

            except asyncio.CancelledError:
                logger.info("Funding rates loop cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in funding loop: {e}", exc_info=True)

            # Sleep for 4 hours
            # We catch asyncio.CancelledError from sleep as well when shutting down
            try:
                await asyncio.sleep(4 * 60 * 60)
            except asyncio.CancelledError:
                logger.info("Funding rates loop cancelled during sleep.")
                break

    finally:
        if should_close_client:
            await client.aclose()
