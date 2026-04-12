import logging
from typing import Any

import httpx
import lxml.html

logger = logging.getLogger(__name__)

async def get_analyst_ratings(client: httpx.AsyncClient, symbol: str) -> list[dict[str, Any]]:
    """
    Fetches the latest analyst ratings for a given stock symbol from Benzinga.

    Args:
        client: Shared httpx.AsyncClient.
        symbol: The stock symbol to query.

    Returns:
        A list of dictionaries representing the analyst ratings.
    """
    url = f"https://www.benzinga.com/quote/{symbol}/analyst-ratings"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    try:
        response = await client.get(url, headers=headers, timeout=10.0)
        response.raise_for_status()
    except Exception as e:
        logger.exception(f"Failed to fetch Benzinga ratings for {symbol}: {e}")
        return []

    try:
        tree = lxml.html.fromstring(response.text)
        tables = tree.xpath('//table')
        if not tables:
            return []

        table = tables[0]
        rows = table.xpath('.//tr')
        if not rows:
            return []

        # Headers are usually in the first row
        header_row = rows[0]
        headers_texts = [th.text_content().strip().replace('▲▼', '').strip() for th in header_row.xpath('.//th | .//td')]

        ratings = []
        for row in rows[1:]:
            cells = [td.text_content().strip() for td in row.xpath('.//td | .//th')]
            if not cells or len(cells) != len(headers_texts):
                continue

            row_dict = {k.lower(): v for k, v in zip(headers_texts, cells)}

            clean_dict = {
                "date": row_dict.get("date", ""),
                "upside_downside": row_dict.get("upside/downside", ""),
                "analyst_firm": row_dict.get("analyst firm", ""),
                "price_target_change": row_dict.get("price target change", ""),
                "rating_change": row_dict.get("rating change", ""),
                "previous_current_rating": row_dict.get("previous / current rating", "")
            }

            # Skip empty rows if they exist
            if not any(clean_dict.values()):
                continue

            ratings.append(clean_dict)

        return ratings
    except Exception as e:
        logger.exception(f"Failed to parse Benzinga ratings for {symbol}: {e}")
        return []
