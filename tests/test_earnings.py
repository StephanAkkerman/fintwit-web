import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_get_earnings_success(async_client: AsyncClient):
    response = await async_client.get("/api/earnings/AAPL", headers={"X-API-Key": "test-api-key"})
    assert response.status_code == 200
    data = response.json()
    assert "stock" in data
    assert data["stock"] == "AAPL"
    assert "next_earnings_date" in data

@pytest.mark.asyncio
async def test_get_earnings_not_found(async_client: AsyncClient):
    response = await async_client.get("/api/earnings/INVALIDTICKER123", headers={"X-API-Key": "test-api-key"})
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "No earnings data" in data["detail"]
