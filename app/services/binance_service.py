import datetime
import logging
from typing import Tuple, List, Dict, Any

import httpx

logger = logging.getLogger(__name__)

async def get_funding_rates(client: httpx.AsyncClient) -> Tuple[List[Dict[str, Any]], datetime.timedelta] | None:
    """
    Gets funding rates for USDT pairs from Binance futures.

    Returns
    -------
    Tuple[List[Dict[str, Any]], datetime.timedelta] | None
        A tuple containing the list of rates (each as a dict with 'symbol' and 'lastFundingRate')
        and the timedelta until the next funding. None if the request failed.
    """
    try:
        response = await client.get("https://fapi.binance.com/fapi/v1/premiumIndex")
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.warning(f"Could not get funding data from Binance: {e}", exc_info=True)
        return None

    if not isinstance(data, list):
        logger.warning("Binance funding data is not a list")
        return None

    usdt_pairs = []
    for item in data:
        symbol = item.get("symbol", "")
        if "USDT" in symbol:
            try:
                rate = float(item.get("lastFundingRate", 0))
                next_funding_time_ms = int(item.get("nextFundingTime", 0))
                usdt_pairs.append({
                    "symbol": symbol.replace("USDT", ""),
                    "lastFundingRate": rate,
                    "nextFundingTime": next_funding_time_ms
                })
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse data for symbol {symbol}: {e}")
                continue

    if not usdt_pairs:
        return None

    # Get time to next funding, unix is in milliseconds
    try:
        next_funding_time = datetime.datetime.fromtimestamp(usdt_pairs[0]["nextFundingTime"] // 1000)
        time_to_next_funding = next_funding_time - datetime.datetime.now()
    except (IndexError, KeyError, ValueError) as e:
        logger.warning(f"Could not calculate next funding time: {e}")
        time_to_next_funding = datetime.timedelta()

    return usdt_pairs, time_to_next_funding
