import httpx
import pandas as pd
from io import StringIO
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

async def get_benzinga_data(stock: str) -> List[Dict] | None:
    """
    Fetches the analyst ratings for a stock from Benzinga.
    """
    url = f"https://www.benzinga.com/quote/{stock}/analyst-ratings"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36 Edg/110.0.1587.57"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            # Read HTML using pandas
            dfs = pd.read_html(StringIO(response.text))
            if not dfs:
                return None

            df = dfs[0]

            # Keep only Date, Price Target Change, Previous / Current Rating
            # The columns usually are: ['Date▲▼', 'Price Target Change▲▼', 'Previous / Current Rating▲▼']

            # Check for exactly these columns and clean them up
            columns_to_keep = []
            for col in df.columns:
                if 'date' in col.lower() or 'price target' in col.lower() or 'rating' in col.lower():
                    columns_to_keep.append(col)

            if not columns_to_keep:
                return None

            # Use unique columns to prevent duplicates
            unique_cols = list(dict.fromkeys(columns_to_keep))
            df = df[unique_cols]

            # Map columns to simpler names
            mapping = {}
            for col in df.columns:
                if 'date' in col.lower():
                    mapping[col] = 'date'
                elif 'price target' in col.lower():
                    mapping[col] = 'target'
                elif 'rating' in col.lower():
                    mapping[col] = 'rating'

            df = df.rename(columns=mapping)

            # Ensure columns are unique after rename
            df = df.loc[:,~df.columns.duplicated()].copy()

            # Drop empty rows or rows that might be headers inside the table
            df = df.dropna(how='all')

            # Limit to 10
            df = df.head(10)

            # Convert to list of dicts
            return df.to_dict('records')

        except Exception as e:
            logger.warning(f"Could not fetch Benzinga data for {stock}: {e}")

    return None
