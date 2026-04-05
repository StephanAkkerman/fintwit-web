import asyncio
import logging
from datetime import datetime, timezone
import httpx

from app.services.barchart_service import get_market_performance
from app.infra.repos import MarketPerformanceRepo

logger = logging.getLogger(__name__)

async def start_market_performance_loop(client: httpx.AsyncClient, repo: MarketPerformanceRepo, interval_seconds: int = 43200):
    """
    Background loop to periodically fetch Barchart market performance and save it to the DB.
    Default interval is 12 hours (43200 seconds) matching the legacy bot.
    """
    while True:
        try:
            logger.info("Fetching market performance data...")
            data = await get_market_performance(client)
            if data:
                # Add updated_at
                now = datetime.now(timezone.utc)
                for item in data:
                    item["updated_at"] = now

                # We need to map keys to snake_case to match the DB columns
                db_items = []
                for item in data:
                    db_item = {
                        "name": item.get("Name"),
                        "ma_5": item.get("5 Day Mov Avg"),
                        "ma_20": item.get("20 Day Mov Avg"),
                        "ma_50": item.get("50 Day Mov Avg"),
                        "ma_100": item.get("100 Day Mov Avg"),
                        "ma_150": item.get("150 Day Mov Avg"),
                        "ma_200": item.get("200 Day Mov Avg"),
                        "updated_at": item.get("updated_at")
                    }
                    if db_item["name"]:
                         db_items.append(db_item)

                count = await repo.upsert_many(db_items)
                logger.info(f"Upserted {count} market performance records.")
            else:
                logger.warning("Failed to fetch market performance data or no data returned.")

        except asyncio.CancelledError:
            logger.info("Market performance loop cancelled.")
            break
        except Exception as e:
            logger.exception(f"Unexpected error in market performance loop: {e}")

        await asyncio.sleep(interval_seconds)
