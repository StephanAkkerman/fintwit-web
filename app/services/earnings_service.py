import logging
from datetime import datetime
import pandas as pd
import pytz
import yfinance
import asyncio

logger = logging.getLogger(__name__)

async def get_earnings_date(ticker_symbol: str) -> dict | None:
    """
    Gets the next earnings date for a given stock ticker.

    Parameters
    ----------
    ticker_symbol : str
        The stock ticker to get the earnings date for.

    Returns
    -------
    dict | None
        A dictionary containing the next earnings date as a timestamp, or None if not found/error.
    """
    try:
        # Run yfinance blockingly in a separate thread since it's synchronous
        def fetch_earnings():
            ticker = yfinance.Ticker(ticker_symbol)
            return ticker.get_earnings_dates()

        df = await asyncio.to_thread(fetch_earnings)

        if df is None or df.empty:
            return None

        # Convert 'today' to a timezone-aware timestamp matching America/New_York
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
            "next_earnings_date": int(closest_date.timestamp()),
            "formatted_date": closest_date.strftime("%Y-%m-%d %H:%M:%S %Z")
        }
    except Exception as e:
        logger.warning(f"Could not fetch earnings date for {ticker_symbol}: {e}")
        return None
