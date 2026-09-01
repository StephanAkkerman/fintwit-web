import httpx
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


async def get_trending_crypto() -> Optional[List[Dict[str, Any]]]:
    """
    Fetches trending crypto data from CoinMarketCap.

    Returns
    -------
    list
        A list of dictionaries containing trending crypto data.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "https://api.coinmarketcap.com/data-api/v3/topsearch/rank"
            )
            response.raise_for_status()
            data = response.json()

            if "data" in data and "cryptoTopSearchRanks" in data["data"]:
                ranks = data["data"]["cryptoTopSearchRanks"]
                results = []
                for item in ranks:
                    price_change = item.get("priceChange", {})
                    results.append(
                        {
                            "name": item.get("name"),
                            "symbol": item.get("symbol"),
                            "slug": item.get("slug"),
                            "price": price_change.get("price"),
                            "change_24h": price_change.get("priceChange24h"),
                            "volume_24h": price_change.get("volume24h"),
                            "website": f"https://coinmarketcap.com/currencies/{item.get('slug')}"
                            if item.get("slug")
                            else None,
                        }
                    )
                return results
        except (
            httpx.RequestError,
            httpx.HTTPStatusError,
            KeyError,
            IndexError,
            ValueError,
        ) as e:
            logger.warning(f"Could not fetch CMC trending crypto data: {e}")

    return None
