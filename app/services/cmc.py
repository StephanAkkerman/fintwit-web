import httpx
import logging

logger = logging.getLogger(__name__)

async def get_trending_coins() -> list[dict] | None:
    """
    Fetches trending crypto coins from CoinMarketCap.

    Returns
    -------
    list[dict]
        A list of dictionaries containing trending coin data.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("https://api.coinmarketcap.com/data-api/v3/topsearch/rank")
            response.raise_for_status()
            data = response.json()

            if "data" in data and "cryptoTopSearchRanks" in data["data"]:
                ranks = data["data"]["cryptoTopSearchRanks"]
                results = []
                for coin in ranks:
                    price_info = coin.get("priceChange", {})
                    results.append({
                        "symbol": coin.get("symbol"),
                        "slug": coin.get("slug"),
                        "name": coin.get("name"),
                        "price": price_info.get("price"),
                        "change_percent": price_info.get("priceChange24h"),
                        "volume": price_info.get("volume24h")
                    })
                return results
        except (httpx.RequestError, httpx.HTTPStatusError, KeyError, IndexError, ValueError, ZeroDivisionError) as e:
            logger.warning(f"Could not fetch trending coins: {e}")

    return None
