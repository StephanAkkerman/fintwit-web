from pydantic import BaseModel

class EarningsResponse(BaseModel):
    stock: str
    next_earnings_date: str
