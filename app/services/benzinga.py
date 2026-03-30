import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Optional

async def get_analyst_ratings(stock: str) -> List[Dict[str, str]]:
    url = f"https://www.benzinga.com/quote/{stock}/analyst-ratings"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": "\"Not_A Brand\";v=\"8\", \"Chromium\";v=\"120\", \"Google Chrome\";v=\"120\"",
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": "\"macOS\"",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.text, "lxml")
            tables = soup.find_all("table")

            if not tables:
                return []

            table = tables[0]
            rows = table.find_all("tr")

            data = []
            # Start from 1 to skip header, we only want top 10 as in original
            for row in rows[1:]:
                tds = row.find_all("td")
                if len(tds) >= 7:
                    date = tds[0].text.strip()
                    # The old code drops 'Buy Now', 'Analyst Firm', 'Analyst & % Accurate', 'Get Alert'
                    # and keeps Date, Price Target Change, Previous / Current Rating.
                    # Looking at our headers:
                    # ['date', 'Buy Now', 'Upside/Downside', 'Analyst Firm', 'Price Target Change', 'Rating Change', 'Previous / Current Rating', 'Get Alert']

                    price_target = tds[4].text.strip()
                    rating = tds[6].text.strip()

                    data.append({
                        "date": date,
                        "price_target": price_target,
                        "rating": rating
                    })

                    if len(data) >= 10:
                        break

            return data
    except Exception as e:
        print(f"Error fetching Benzinga data: {e}")
        return []
