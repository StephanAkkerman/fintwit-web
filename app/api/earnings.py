from datetime import datetime

import pandas as pd
import pytz
import yfinance as yf
from fastapi import APIRouter, HTTPException, Depends, Request
from app.schemas.earnings import EarningsResponse

async def get_api_key_dep(request: Request):
    expected = getattr(request.app.state, "API_KEY", "")
    got = request.headers.get("X-API-Key")
    if expected and got != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


router = APIRouter()

@router.get("/api/earnings/{stock}", response_model=EarningsResponse)
def get_earnings(stock: str, _=Depends(get_api_key_dep)):
    """
    Gets next earnings date for a given stock.
    """
    try:
        ticker = yf.Ticker(stock)
        df = ticker.get_earnings_dates()

        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="No earnings data found for this stock")

        # Convert 'today' to a timezone-aware timestamp
        tz = pytz.timezone("America/New_York")
        today = pd.Timestamp(datetime.now(tz))

        # Filter the DataFrame to include only future dates
        future_dates = df[df.index > today]

        if future_dates.empty:
            raise HTTPException(status_code=404, detail="No future earnings dates found for this stock")

        # Find the closest date
        closest_date = future_dates.index.min()

        return EarningsResponse(
            stock=stock.upper(),
            next_earnings_date=closest_date.isoformat()
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
