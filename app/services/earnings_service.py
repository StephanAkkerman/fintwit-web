import yfinance
import pandas as pd
from datetime import datetime
import pytz
import asyncio

async def get_next_earnings_date(ticker_symbol: str) -> dict | None:
    """
    Fetches the next earnings date for a given ticker symbol using yfinance.

    Parameters
    ----------
    ticker_symbol : str
        The stock ticker, e.g., 'AAPL'.

    Returns
    -------
    dict | None
        A dictionary with the ticker and the next earnings date as an ISO string, or None if not found/error.
    """
    def _fetch():
        try:
            ticker = yfinance.Ticker(ticker_symbol)
            df = ticker.get_earnings_dates()

            if df is None or df.empty:
                return None

            # Convert 'today' to a timezone-aware timestamp
            tz = pytz.timezone("America/New_York")
            today = pd.Timestamp(datetime.now(tz))

            # Filter the DataFrame to include only future dates
            future_dates = df[df.index > today]

            if future_dates.empty:
                return None

            # Find the closest date
            closest_date = future_dates.index.min()

            return {
                "ticker": ticker_symbol.upper(),
                "next_earnings_date": closest_date.isoformat(),
                "timestamp": int(closest_date.timestamp())
            }
        except Exception:
            return None

    # Run the blocking yfinance call in a thread pool
    return await asyncio.to_thread(_fetch)
