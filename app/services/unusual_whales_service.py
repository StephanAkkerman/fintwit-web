import httpx
import logging

logger = logging.getLogger(__name__)

async def get_spy_heatmap(client: httpx.AsyncClient, date_range: str = "one_day") -> list[dict]:
    """
    Fetches the S&P 500 heatmap data from Unusual Whales API.

    Parameters
    ----------
    client: httpx.AsyncClient
    date_range : str, optional
        Options are: one_day, after_hours, yesterday, one_week, one_month, ytd, one_year, by default "one_day"

    Returns
    -------
    list[dict]
        The S&P 500 heatmap data as a list of dicts.
    """
    url = f"https://phx.unusualwhales.com/api/etf/SPY/heatmap?date_range={date_range}"
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.54 Safari/537.36"
    }

    try:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        items = data.get("data", [])
        result = []
        for row in items:
            marketcap = float(row.get("marketcap") or 0)
            if marketcap <= 0:
                continue

            close = float(row.get("close") or 0)
            prev_close = float(row.get("prev_close") or close)
            percentage_change = 0.0
            if prev_close != 0:
                percentage_change = ((close - prev_close) / prev_close) * 100

            result.append({
                "ticker": row.get("ticker", ""),
                "sector": row.get("sector", ""),
                "industry": row.get("industry", ""),
                "marketcap": marketcap,
                "close": close,
                "prev_close": prev_close,
                "percentage_change": percentage_change,
                "call_volume": int(row.get("call_volume") or 0),
                "put_volume": int(row.get("put_volume") or 0),
                "call_premium": float(row.get("call_premium") or 0),
                "put_premium": float(row.get("put_premium") or 0),
            })

        return result
    except Exception as e:
        logger.exception(f"Failed to fetch SPY heatmap: {e}")
        return []
