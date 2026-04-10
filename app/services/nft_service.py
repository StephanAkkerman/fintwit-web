import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_TRENDING_NFTS_URL = "https://api.coingecko.com/api/v3/search/trending"


def _to_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


async def get_trending_nfts(
    client: httpx.AsyncClient, limit: int = 10
) -> Optional[list[dict]]:
    """Fetch trending NFTs from CoinGecko search/trending endpoint."""
    try:
        response = await client.get(_TRENDING_NFTS_URL)
        if response.status_code != 200:
            logger.warning(
                "Could not fetch CoinGecko trending NFTs: status=%s",
                response.status_code,
            )
            return None
        payload = response.json()
    except (httpx.RequestError, ValueError) as exc:
        logger.warning("Could not fetch CoinGecko trending NFTs: %s", exc)
        return None

    items = payload.get("nfts")
    if not isinstance(items, list):
        return []

    results: list[dict] = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue

        nft_id = str(item.get("id") or "").strip()
        floor_currency = str(item.get("native_currency_symbol") or "").strip().upper()

        results.append(
            {
                "id": nft_id or None,
                "name": str(item.get("name") or "").strip() or "Unknown",
                "symbol": str(item.get("symbol") or "").strip().upper() or None,
                "thumb": str(item.get("thumb") or "").strip() or None,
                "floor_price": _to_float(item.get("floor_price_in_native_currency")),
                "floor_currency": floor_currency or None,
                "floor_change_24h": _to_float(
                    item.get("floor_price_24h_percentage_change")
                ),
                "website": (
                    f"https://www.coingecko.com/en/nft/{nft_id}" if nft_id else None
                ),
            }
        )

    return results
