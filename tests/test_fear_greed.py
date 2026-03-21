from unittest.mock import patch
import pytest
from httpx import ASGITransport, AsyncClient
from app.api.main import app

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.asyncio
async def test_fear_greed_endpoint():
    mock_data = {
        "value": 50,
        "change_percent": 1.5,
        "classification": "Neutral"
    }

    with patch("app.api.main.get_fear_greed") as mock_get_fear_greed:
        mock_get_fear_greed.return_value = mock_data

        # Override the API_KEY for the test
        app.state.API_KEY = "test"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/fear-greed", headers={"X-API-Key": "test"})

        assert response.status_code == 200
        assert response.json() == mock_data

@pytest.mark.asyncio
async def test_fear_greed_endpoint_unavailable():
    with patch("app.api.main.get_fear_greed") as mock_get_fear_greed:
        mock_get_fear_greed.return_value = None

        # Override the API_KEY for the test
        app.state.API_KEY = "test"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/fear-greed", headers={"X-API-Key": "test"})

        assert response.status_code == 503
        assert response.json() == {"detail": "Fear and Greed index unavailable"}
