import asyncio
import httpx
from typing import List, Dict, Any
from ..schemas.yahoo import TickerData, MarketMoversResponse

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36 Edg/110.0.1587.57"
}

async def get_json_data(url: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(headers=HEADERS) as client:
        try:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return {}

def _parse_quotes(data: Dict[str, Any]) -> List[TickerData]:
    quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
    parsed = []
    for q in quotes:
        symbol = q.get("symbol")
        if not symbol:
            continue
        parsed.append(TickerData(
            symbol=symbol,
            name=q.get("shortName") or q.get("longName"),
            price=q.get("regularMarketPrice"),
            change=q.get("regularMarketChange"),
            change_percent=q.get("regularMarketChangePercent")
        ))
    return parsed

async def get_gainers(count: int = 10) -> List[TickerData]:
    url = f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&lang=en-US&region=US&scrIds=day_gainers&count={count}&corsDomain=finance.yahoo.com"
    data = await get_json_data(url)
    return _parse_quotes(data)

async def get_losers(count: int = 10) -> List[TickerData]:
    url = f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&lang=en-US&region=US&scrIds=day_losers&count={count}&corsDomain=finance.yahoo.com"
    data = await get_json_data(url)
    return _parse_quotes(data)

async def get_trending(count: int = 10) -> List[TickerData]:
    url = f"https://query1.finance.yahoo.com/v1/finance/trending/US?count={count}"
    data = await get_json_data(url)
    return _parse_quotes(data)

async def get_market_movers(count: int = 10) -> MarketMoversResponse:
    trending_task = get_trending(count)
    gainers_task = get_gainers(count)
    losers_task = get_losers(count)

    trending, gainers, losers = await asyncio.gather(
        trending_task, gainers_task, losers_task, return_exceptions=True
    )

    return MarketMoversResponse(
        trending=trending if isinstance(trending, list) else [],
        gainers=gainers if isinstance(gainers, list) else [],
        losers=losers if isinstance(losers, list) else []
    )
