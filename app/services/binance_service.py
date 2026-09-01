import logging
from typing import Dict, Any

import httpx

logger = logging.getLogger(__name__)


async def get_gainers_losers(client: httpx.AsyncClient) -> Dict[str, Any] | None:
    """
    Fetches the 24hr ticker data from Binance, filters for USDT pairs,
    and returns the top 10 gainers and top 10 losers sorted by priceChangePercent.

    Returns:
        A dictionary containing "gainers" and "losers" lists of dicts.
    """
    url = "https://api.binance.com/api/v3/ticker/24hr"

    try:
        response = await client.get(url)
        response.raise_for_status()
        binance_data = response.json()
    except Exception as e:
        logger.exception(f"Could not fetch Binance ticker data: {e}")
        return None

    if not isinstance(binance_data, list):
        logger.warning(
            f"Unexpected response type from Binance API: {type(binance_data)}"
        )
        return None

    parsed_data = []

    for item in binance_data:
        symbol = item.get("symbol", "")
        if "USDT" in symbol:
            try:
                base_symbol = symbol.replace("USDT", "")
                price_change_percent = float(item.get("priceChangePercent", 0))
                price = float(item.get("weightedAvgPrice", 0))
                volume = float(item.get("volume", 0))

                parsed_data.append(
                    {
                        "symbol": base_symbol,
                        "price_change_percent": price_change_percent,
                        "price": price,
                        "volume": volume,
                        "website": f"https://www.binance.com/en/price/{base_symbol}",
                    }
                )
            except (ValueError, TypeError) as e:
                logger.debug(f"Could not parse data for symbol {symbol}: {e}")
                continue

    if not parsed_data:
        return None

    # Sort on priceChangePercent, descending
    sorted_data = sorted(
        parsed_data, key=lambda x: x["price_change_percent"], reverse=True
    )

    # Top 10 highest
    gainers = sorted_data[:10]

    # Top 10 lowest
    losers = sorted_data[-10:]
    # reverse losers so it is sorted from most negative to least negative
    losers.reverse()

    return {"gainers": gainers, "losers": losers}
