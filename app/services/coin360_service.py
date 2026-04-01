import httpx
import logging

logger = logging.getLogger(__name__)

async def get_treemap_data() -> dict | None:
    """
    Fetches the latest cryptocurrency Treemap data from Coin360 API.

    Returns
    -------
    dict | None
        The JSON response from Coin360 containing categories and data blocks,
        or None if an error occurred.
    """
    url = "https://coin360.com/site-api/coins?currency=USD&period=24h&ranking=top100"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as e:
            logger.exception(f"Could not fetch Treemap data from Coin360: {e}")
            return None
