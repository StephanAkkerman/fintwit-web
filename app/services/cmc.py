import aiohttp
import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

async def get_trending_crypto() -> Optional[List[Dict]]:
    url = "https://api.coinmarketcap.com/data-api/v3/topsearch/rank"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

                    if "data" not in data or "cryptoTopSearchRanks" not in data["data"]:
                        return None

                    ranks = data["data"]["cryptoTopSearchRanks"]
                    results = []

                    for item in ranks:
                        symbol = item.get("symbol")
                        slug = item.get("slug")
                        price_change = item.get("priceChange", {})

                        price = price_change.get("price", 0.0)
                        change_percent = price_change.get("priceChange24h", 0.0)
                        volume = price_change.get("volume24h", 0.0)

                        results.append({
                            "symbol": symbol,
                            "slug": slug,
                            "price": price,
                            "change_percent": change_percent,
                            "volume": volume,
                            "website": f"https://coinmarketcap.com/currencies/{slug}" if slug else ""
                        })

                    return results
    except Exception:
        logger.exception("Error fetching trending crypto from CoinMarketCap")
        pass

    return None
