import asyncio
import httpx
import logging

from ..infra.repos import SPYHeatmapRepo
from ..services.unusual_whales_service import get_spy_heatmap

logger = logging.getLogger(__name__)

async def run_spy_heatmap_worker(repo: SPYHeatmapRepo, client: httpx.AsyncClient) -> None:
    while True:
        try:
            data = await get_spy_heatmap(client)
            if data:
                await repo.upsert_many(data)
                logger.info(f"Updated {len(data)} items in SPY heatmap")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception(f"[spy-heatmap-worker] error: {e!r}")

        # Sleep for 1 hour
        await asyncio.sleep(3600)
