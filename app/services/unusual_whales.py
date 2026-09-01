import logging
import httpx

logger = logging.getLogger(__name__)


async def get_spy_heatmap(
    client: httpx.AsyncClient, date: str = "one_day"
) -> dict | None:
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


def _to_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _finalize_bucket(bucket: dict) -> dict:
    market_cap = bucket["market_cap"]
    change_percent = bucket["weighted_change"] / market_cap if market_cap else None
    return {
        "market_cap": market_cap,
        "change_percent": change_percent,
        "stock_count": bucket["stock_count"],
    }


def summarize_spy_sectors(payload: dict | None) -> list[dict]:
    """
    Groups SPY heatmap constituents into sector/subsector performance.

    A plain GICS sector (e.g. "Technology") is too coarse to see a narrow
    move -- semiconductors selling off inside an otherwise flat sector, for
    example -- so each sector is also broken down by its constituents'
    ``industry`` (subsector).

    Parameters
    ----------
    payload : dict | None
        Raw ``{"data": [...]}`` payload as returned by ``get_spy_heatmap``.

    Returns
    -------
    list[dict]
        Sectors sorted by market cap, largest first. Each entry has
        ``sector``, a market-cap-weighted average ``change_percent``,
        ``market_cap``, ``stock_count``, and a ``subsectors`` list (same
        shape, keyed by ``industry``) sorted the same way.
    """
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []

    sectors: dict[str, dict] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue

        sector = str(row.get("sector") or "").strip() or "Unknown"
        industry = str(row.get("industry") or "").strip() or "Other"
        market_cap = _to_float(row.get("marketcap")) or 0.0
        close = _to_float(row.get("close"))
        prev_close = _to_float(row.get("prev_close"))

        change_percent = None
        if close is not None and prev_close:
            change_percent = (close - prev_close) / prev_close * 100

        sector_bucket = sectors.setdefault(
            sector,
            {
                "market_cap": 0.0,
                "weighted_change": 0.0,
                "stock_count": 0,
                "subsectors": {},
            },
        )
        sector_bucket["stock_count"] += 1
        sector_bucket["market_cap"] += market_cap
        if change_percent is not None:
            sector_bucket["weighted_change"] += change_percent * market_cap

        sub_bucket = sector_bucket["subsectors"].setdefault(
            industry,
            {"market_cap": 0.0, "weighted_change": 0.0, "stock_count": 0},
        )
        sub_bucket["stock_count"] += 1
        sub_bucket["market_cap"] += market_cap
        if change_percent is not None:
            sub_bucket["weighted_change"] += change_percent * market_cap

    result = []
    for sector, bucket in sectors.items():
        subsectors = [
            {"industry": industry, **_finalize_bucket(sub)}
            for industry, sub in bucket["subsectors"].items()
        ]
        subsectors.sort(key=lambda s: s["market_cap"], reverse=True)
        result.append(
            {"sector": sector, **_finalize_bucket(bucket), "subsectors": subsectors}
        )

    result.sort(key=lambda s: s["market_cap"], reverse=True)
    return result


if __name__ == "__main__":
    import asyncio

    async def main():
        async with httpx.AsyncClient() as client:
            data = await get_spy_heatmap(client)
            if data:
                print(
                    f"Heatmap data fetched successfully. Returned {len(data.get('data', []))} records."
                )
            else:
                print("Failed to fetch SPY heatmap data.")

    asyncio.run(main())
