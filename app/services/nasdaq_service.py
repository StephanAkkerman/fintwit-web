import logging
from io import StringIO
import datetime
from dateutil import tz
import httpx
import lxml.html

logger = logging.getLogger(__name__)

async def get_halt_data(client: httpx.AsyncClient) -> list[dict] | None:
    """
    Fetches the halted stocks data from Nasdaq.

    Parameters
    ----------
    client : httpx.AsyncClient
        The HTTP client to use for the request.

    Returns
    -------
    list[dict] | None
        A list of dictionaries representing halted stocks for the current day.
        Each dict contains: 'Time', 'Issue Symbol', and optionally 'Resumption Time'.
        Returns None if an error occurs.
    """
    html = await fetch_halt_data(client)
    if not html or "result" not in html:
        return None

    try:
        # Parse the HTML table using lxml
        tree = lxml.html.parse(StringIO(html["result"]))
        tables = tree.xpath("//table")
        if not tables:
            return []

        table = tables[0]
        rows = table.xpath(".//tr")
        if len(rows) <= 1: # Header only or empty
            return []

        # Extract headers to find column indices
        headers = [th.text_content().strip() for th in rows[0].xpath(".//th")]

        col_indices = {}
        for idx, header in enumerate(headers):
            col_indices[header] = idx

        required_cols = ["Halt Date", "Halt Time", "Issue Symbol"]
        if not all(col in col_indices for col in required_cols):
             logger.warning(f"Nasdaq halt data missing required columns. Found: {headers}")
             return []

        has_resumption = "Resumption Date" in col_indices and "Resumption Trade Time" in col_indices

        today_str = datetime.datetime.now().strftime("%m/%d/%Y")
        halts = []

        for row in rows[1:]:
            cols = row.xpath(".//td")
            if len(cols) != len(headers):
                 continue

            row_data = {headers[i]: cols[i].text_content().strip() for i in range(len(headers))}

            halt_date = row_data.get("Halt Date")
            if halt_date != today_str:
                continue

            halt_time = row_data.get("Halt Time")
            issue_symbol = row_data.get("Issue Symbol")

            # Combine columns into one singular datetime column
            try:
                dt_str = f"{halt_date} {halt_time}"
                dt = datetime.datetime.strptime(dt_str, "%m/%d/%Y %H:%M:%S")
                dt_eastern = dt.replace(tzinfo=tz.gettz("US/Eastern"))
                time_str = dt_eastern.strftime("%H:%M:%S")
            except ValueError:
                time_str = "?"

            halt_dict = {
                "Time": time_str,
                "Issue Symbol": issue_symbol if issue_symbol else "?"
            }

            if has_resumption:
                res_date = row_data.get("Resumption Date")
                res_time = row_data.get("Resumption Trade Time")
                if res_date and res_time and res_date != "" and res_time != "":
                    try:
                         res_dt_str = f"{res_date} {res_time}"
                         res_dt = datetime.datetime.strptime(res_dt_str, "%m/%d/%Y %H:%M:%S")
                         res_dt_eastern = res_dt.replace(tzinfo=tz.gettz("US/Eastern"))
                         halt_dict["Resumption Time"] = res_dt_eastern.strftime("%H:%M:%S")
                    except ValueError:
                         halt_dict["Resumption Time"] = "?"
                else:
                     halt_dict["Resumption Time"] = "?"

            halts.append(halt_dict)

        return halts
    except Exception as e:
        logger.exception(f"Error parsing Nasdaq halt data: {e}")
        return None

async def fetch_halt_data(client: httpx.AsyncClient) -> dict | None:
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://www.nasdaqtrader.com",
        "Referer": "https://www.nasdaqtrader.com/trader.aspx?id=tradehalts",
        "Sec-Ch-Ua": '"Not.A/Brand";v="8", "Chromium";v="114", "Google Chrome";v="114"',
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    }
    req_data = {
        "id": 3,
        "method": "BL_TradeHalt.GetTradeHalts",
        "params": "[]",
        "version": "1.1",
    }

    url = "https://www.nasdaqtrader.com/RPCHandler.axd"

    try:
        response = await client.post(url, headers=headers, json=req_data)
        response.raise_for_status()
        return response.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as e:
        logger.exception(f"Could not fetch halt data from Nasdaq: {e}")
        return None
