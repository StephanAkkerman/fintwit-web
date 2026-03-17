from pydantic import BaseModel
from typing import List, Optional

class TickerData(BaseModel):
    symbol: str
    name: Optional[str] = None
    price: Optional[float] = None
    change: Optional[float] = None
    change_percent: Optional[float] = None

class MarketMoversResponse(BaseModel):
    trending: List[TickerData] = []
    gainers: List[TickerData] = []
    losers: List[TickerData] = []
