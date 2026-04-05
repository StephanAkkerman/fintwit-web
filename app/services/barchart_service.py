import logging
import httpx
from lxml import html
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

async def get_market_performance(client: httpx.AsyncClient) -> Optional[List[Dict[str, Any]]]:
    """
    Fetches the market performance data from Barchart and parses the HTML table.

    Parameters
    ----------
    client : httpx.AsyncClient
        The HTTP client to use for the request.

    Returns
    -------
    list
        A list of dictionaries containing market performance data.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
    }
    url = "https://www.barchart.com/stocks/market-performance"

    try:
        response = await client.get(url, headers=headers)
        response.raise_for_status()

        # Parse HTML
        tree = html.fromstring(response.text)
        tables = tree.xpath("//table")
        if not tables:
            logger.warning("No tables found in Barchart response.")
            return None

        # The first table is usually the target
        table = tables[0]

        # Extract headers
        headers_xpath = table.xpath(".//th")
        if not headers_xpath:
             # Sometimes headers are in the first row's td
            first_row = table.xpath(".//tr")[0]
            headers_xpath = first_row.xpath(".//td")
            rows = table.xpath(".//tr")[1:]
        else:
            rows = table.xpath(".//tr")[1:] # skip header row

        columns = [th.text_content().strip() for th in headers_xpath]

        results = []
        for row in rows:
            cells = row.xpath(".//td")
            if len(cells) != len(columns):
                continue

            row_data = {}
            for i, cell in enumerate(cells):
                col_name = columns[i]
                val = cell.text_content().strip()
                # Remove % from all rows
                val = val.replace("%", "")

                # Convert numeric columns
                if col_name in [
                    "5 Day Mov Avg",
                    "20 Day Mov Avg",
                    "50 Day Mov Avg",
                    "100 Day Mov Avg",
                    "150 Day Mov Avg",
                    "200 Day Mov Avg",
                ]:
                    try:
                        val = float(val) if '.' in val else int(val)
                    except ValueError:
                        pass

                row_data[col_name] = val

            # The original barchart.py expected 'Name'
            if "Name" not in row_data and columns and "Name" not in columns:
                # Rename the first column to Name if it exists
                if len(columns) > 0:
                    row_data["Name"] = row_data.pop(columns[0])

            results.append(row_data)

        return results

    except (httpx.RequestError, httpx.HTTPStatusError, ValueError, IndexError) as e:
        logger.exception(f"Could not fetch Barchart market performance: {e}")
        return None

if __name__ == "__main__":
    import asyncio

    async def main():
        async with httpx.AsyncClient() as client:
            data = await get_market_performance(client)
            if data:
                print(f"Data fetched successfully. Returned {len(data)} records.")
                print(data[0])
            else:
                print("Failed to fetch market performance data.")

    asyncio.run(main())
