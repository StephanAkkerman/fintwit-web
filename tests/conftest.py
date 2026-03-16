import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.main import app


@pytest_asyncio.fixture
async def async_client():
    # httpx ASGITransport does not guarantee FastAPI lifespan startup in tests,
    # so initialize auth state explicitly for dependency checks.
    app.state.API_KEY = "test-api-key"
    # ASGITransport is the modern way to test FastAPI apps with httpx
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
