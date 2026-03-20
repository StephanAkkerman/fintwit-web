import httpx

async def get_feargreed() -> dict | None:
    """
    Gets the last 2 Fear and Greed indices from the API.

    Returns
    -------
    dict
        A dictionary containing today's index and the percentual change.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("https://api.alternative.me/fng/?limit=2")
            response.raise_for_status()
            data = response.json()

            if "data" in data and len(data["data"]) >= 2:
                today = int(data["data"][0]["value"])
                yesterday = int(data["data"][1]["value"])

                change = 0.0
                if yesterday > 0:
                    change = round((today - yesterday) / yesterday * 100, 2)

                return {
                    "value": today,
                    "change": change,
                    "status": data["data"][0]["value_classification"],
                }
                }
        except Exception:
            pass

    return None
