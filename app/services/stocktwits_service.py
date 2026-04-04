import httpx
import logging

logger = logging.getLogger(__name__)

async def get_stocktwits_data(client: httpx.AsyncClient, keyword: str) -> list[dict] | None:
    """
    Gets the data from StockTwits based on the passed keywords.

    Parameters
    ----------
    client : httpx.AsyncClient
        The HTTP client to use for the request.
    keyword : str
        The specific keyword to get the data for. Options are: ts, m_day, wl_ct_day.

    Returns
    -------
    list[dict] | None
        A list of dictionaries representing the stocktwits rankings, or None if an error occurred.
    """
    if keyword not in ["ts", "m_day", "wl_ct_day"]:
        logger.warning(f"Invalid keyword for StockTwits: {keyword}")
        return None

    url = f"https://api.stocktwits.com/api/2/charts/{keyword}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

    try:
        response = await client.get(url, headers=headers, follow_redirects=True)
        response.raise_for_status()
        data = response.json()

        if not data or "table" not in data or keyword not in data["table"]:
            return []

        table_data = data["table"][keyword]
        stocks_data = data.get("stocks", {})

        merged_data = []
        for item in table_data:
            stock_id_str = str(item.get("stock_id", ""))
            stock_info = stocks_data.get(stock_id_str, {})

            # Merge table item and stock info
            merged_item = {**stock_info, **item}
            merged_data.append(merged_item)

        # Sort by 'val' descending
        merged_data.sort(key=lambda x: float(x.get("val", 0) or 0), reverse=True)

        formatted_data = []
        for item in merged_data:
            price = float(item.get("price") or 0)
            change = float(item.get("change") or 0)

            # Format % change
            if change > 0:
                change_str = f" (+{round(change, 2)}% 📈)"
            else:
                change_str = f" ({round(change, 2)}% 📉)"

            # Format price
            formatted_price = f"{round(price, 3)}{change_str}"

            formatted_data.append({
                "stock_id": item.get("stock_id"),
                "symbol": str(item.get("symbol", "")),
                "name": str(item.get("name", "")),
                "price": formatted_price,
                "val": str(item.get("val", "")),
            })

        return formatted_data
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError, TypeError, KeyError) as e:
        logger.exception(f"Could not fetch or process data from StockTwits: {e}")
        return None
