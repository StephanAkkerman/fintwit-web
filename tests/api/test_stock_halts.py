import pytest
from unittest.mock import patch, AsyncMock
from httpx import ASGITransport
import datetime
from dateutil import tz
from app.api.main import app

import pytest_asyncio


@pytest_asyncio.fixture
async def async_client():
    from httpx import AsyncClient

    # Setup state that the lifespan context manager would normally provide
    app.state.http_client = AsyncClient()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await app.state.http_client.aclose()


MOCK_HTML_RESPONSE = """
<html>
<body>
<table>
    <tr>
        <th>Halt Date</th>
        <th>Halt Time</th>
        <th>Issue Symbol</th>
        <th>Resumption Date</th>
        <th>Resumption Trade Time</th>
    </tr>
    <tr>
        <td>{today}</td>
        <td>09:30:00</td>
        <td>MOCK</td>
        <td>{today}</td>
        <td>10:00:00</td>
    </tr>
    <tr>
        <td>{today}</td>
        <td>10:00:00</td>
        <td>HALT</td>
        <td></td>
        <td></td>
    </tr>
</table>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_get_stock_halts_success(async_client):
    # get_halt_data filters rows by today's date in US/Eastern (Nasdaq's
    # timezone), which can differ from the naive local date -- e.g. any time
    # before ~20:00 US/Eastern is still "today" there but already tomorrow in
    # UTC. Match that timezone so the test doesn't flip failing after midnight
    # UTC.
    today = datetime.datetime.now(tz.gettz("US/Eastern")).strftime("%m/%d/%Y")
    mock_html = MOCK_HTML_RESPONSE.format(today=today)

    mock_fetch = AsyncMock(return_value={"result": mock_html})

    with patch("app.services.nasdaq_service.fetch_halt_data", mock_fetch):
        response = await async_client.get(
            "/api/stock-halts", headers={"X-API-Key": "dev-secret-key"}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["Issue Symbol"] == "MOCK"
        assert data[0]["Resumption Time"] != "?"
        assert data[1]["Issue Symbol"] == "HALT"
        assert data[1]["Resumption Time"] == "?"


@pytest.mark.asyncio
async def test_get_stock_halts_error(async_client):
    mock_fetch = AsyncMock(return_value=None)

    with patch("app.services.nasdaq_service.fetch_halt_data", mock_fetch):
        response = await async_client.get(
            "/api/stock-halts", headers={"X-API-Key": "dev-secret-key"}
        )
        assert response.status_code == 503
        assert response.json() == {"detail": "Service Unavailable"}


@pytest.mark.asyncio
async def test_get_stock_halts_unauthorized(async_client):
    app.state.API_KEY = "dev-secret-key"
    response = await async_client.get("/api/stock-halts")
    assert response.status_code == 401
