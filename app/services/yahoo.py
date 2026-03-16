import aiohttp
from typing import Optional, Tuple

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36 Edg/110.0.1587.57"
}

async def get_stock_info(ticker: str) -> Optional[dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    result = data.get("chart", {}).get("result")
                    if not result:
                        return None
                    meta = result[0].get("meta", {})

                    price = meta.get("regularMarketPrice")
                    prev_close = meta.get("previousClose", price)

                    if price is None:
                        return None

                    change = 0.0
                    if prev_close and prev_close != 0:
                        change = ((price - prev_close) / prev_close) * 100

                    volume = meta.get("regularMarketVolume", 0) * price if price else 0

                    return {
                        "price": price,
                        "change_percent": change,
                        "volume": volume,
                        "website": f"https://finance.yahoo.com/quote/{ticker}"
                    }
        except Exception:
            pass

    return None
