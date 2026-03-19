import aiohttp
from typing import Optional

async def get_crypto_info(ticker: str) -> Optional[dict]:
    url = f"https://api.coingecko.com/api/v3/search?query={ticker}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    coins = data.get("coins", [])
                    if coins:
                        coin = coins[0]
                        coin_id = coin.get("id")

                        # Get price and volume
                        price_url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_market_cap=false&include_24hr_vol=true&include_24hr_change=true&include_last_updated_at=false"
                        async with session.get(price_url) as price_response:
                            if price_response.status == 200:
                                price_data = await price_response.json()
                                if coin_id in price_data:
                                    info = price_data[coin_id]
                                    return {
                                        "price": info.get("usd", 0.0),
                                        "change_percent": info.get("usd_24h_change", 0.0),
                                        "volume": info.get("usd_24h_vol", 0.0),
                                        "website": f"https://www.coingecko.com/en/coins/{coin_id}"
                                    }
    except Exception:
        pass

    return None
