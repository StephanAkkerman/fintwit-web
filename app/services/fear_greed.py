import aiohttp
from typing import Optional

async def get_fear_greed() -> Optional[dict]:
    """
    Gets the last 2 Fear and Greed indices from the API.

    Returns
    -------
    dict
        A dictionary containing today's value, yesterday's value, the percentage change, and the current value classification.
    """
    url = "https://api.alternative.me/fng/?limit=2"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

                    if "data" in data:
                        today = int(data["data"][0]["value"])
                        yesterday = int(data["data"][1]["value"])
                        classification = data["data"][0]["value_classification"]

                        change = 0.0
                        if yesterday != 0:
                            change = round((today - yesterday) / yesterday * 100, 2)

                        return {
                            "value": today,
                            "change_percent": change,
                            "classification": classification,
                        }
    except Exception:
        pass

    return None
