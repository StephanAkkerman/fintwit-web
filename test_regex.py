import re
import asyncio
import httpx

async def get_analyst_ratings(stock: str):
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

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        html = response.text

        tbody_match = re.search(r'<tbody[^>]*>(.*?)</tbody>', html, re.IGNORECASE | re.DOTALL)
        if not tbody_match:
            print("No tbody found")
            return []

        tbody = tbody_match.group(1)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbody, re.IGNORECASE | re.DOTALL)

        data = []
        for row in rows:
            cols = re.findall(r'<td[^>]*>(.*?)</td>', row, re.IGNORECASE | re.DOTALL)
            cols_text = [re.sub(r'<[^>]+>', '', col).strip() for col in cols]

            if len(cols_text) >= 7:
                date = cols_text[0]
                price_target = cols_text[4]
                rating = cols_text[6]

                data.append({
                    "date": date,
                    "price_target": price_target,
                    "rating": rating
                })

                if len(data) >= 10:
                    break

        return data

print(asyncio.run(get_analyst_ratings("AAPL")))
