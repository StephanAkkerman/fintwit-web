import httpx
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

async def get_all_usdt_tickers(client: httpx.AsyncClient) -> list[dict]:
    """
    Fetches the 24hr ticker data from Binance, filters for USDT pairs,
    and returns a list of dictionaries with normalized data.
    """
    try:
        response = await client.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10.0)
        response.raise_for_status()
        data = response.json()
    except Exception:
        logger.exception("Failed to fetch data from Binance API")
        return []

    now = datetime.now(timezone.utc)
    results = []

    for item in data:
        symbol = item.get("symbol", "")
        if not symbol.endswith("USDT"):
            continue

        base_symbol = symbol[:-4]  # Remove "USDT"

        try:
            results.append({
                "symbol": base_symbol,
                "price_change_percent": float(item.get("priceChangePercent", 0.0)),
                "last_price": float(item.get("lastPrice", 0.0)),
                "volume": float(item.get("volume", 0.0)),
                "updated_at": now
            })
        except (ValueError, TypeError):
            logger.warning("Could not parse numeric data for symbol %s: %s", symbol, item)

    return results
