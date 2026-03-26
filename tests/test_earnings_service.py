import pytest
from app.services.earnings_service import get_earnings_date

@pytest.mark.asyncio
async def test_get_earnings_date_valid():
    res = await get_earnings_date("AAPL")
    assert res is not None
    assert res["ticker"] == "AAPL"
    assert "next_earnings_date" in res

@pytest.mark.asyncio
async def test_get_earnings_date_invalid():
    res = await get_earnings_date("INVALIDTICKER123")
    assert res is None
