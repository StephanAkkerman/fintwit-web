import logging
import httpx

logger = logging.getLogger(__name__)

async def get_spy_heatmap(client: httpx.AsyncClient, date: str = "one_day") -> dict | None:
    """
    Fetches the S&P 500 heatmap data from Unusual Whales API.

    Parameters
    ----------
    client : httpx.AsyncClient
        The HTTP client to use for the request.
    date : str, optional
        Options are: one_day, after_hours, yesterday, one_week, one_month, ytd, one_year, by default "one_day"

    Returns
    -------
    dict | None
        The JSON response from Unusual Whales containing the heatmap data,
        or None if an error occurred.
    """
    url = "https://phx.unusualwhales.com/api/etf/SPY/heatmap"
    params = {"date_range": date}
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.54 Safari/537.36"
    }

    try:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as e:
        logger.exception(f"Could not fetch SPY heatmap data from Unusual Whales: {e}")
        return None

if __name__ == "__main__":
    import asyncio

    async def main():
        async with httpx.AsyncClient() as client:
            data = await get_spy_heatmap(client)
            if data:
                print(f"Heatmap data fetched successfully. Returned {len(data.get('data', []))} records.")
            else:
                print("Failed to fetch SPY heatmap data.")

    asyncio.run(main())
