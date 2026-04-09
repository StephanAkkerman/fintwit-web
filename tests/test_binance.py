import pytest
import pytest_asyncio
from datetime import datetime, timezone

from app.infra.db import create_engine, init_db
from app.infra.repos import BinanceTickerRepo
from sqlalchemy.ext.asyncio import async_sessionmaker


@pytest_asyncio.fixture
async def binance_repo():
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    yield BinanceTickerRepo(Session)
    await engine.dispose()


@pytest.mark.asyncio
async def test_upsert_many(binance_repo):
    now = datetime.now(timezone.utc)
    items = [
        {
            "symbol": "BTC",
            "price_change_percent": 5.0,
            "last_price": 60000.0,
            "volume": 1000.0,
            "updated_at": now,
        },
        {
            "symbol": "ETH",
            "price_change_percent": -2.0,
            "last_price": 3000.0,
            "volume": 5000.0,
            "updated_at": now,
        },
    ]

    await binance_repo.upsert_many(items)

    gainers, losers = await binance_repo.get_gainers_losers(limit=10)
    assert len(gainers) == 2
    assert len(losers) == 2

    assert gainers[0]["symbol"] == "BTC"
    assert gainers[1]["symbol"] == "ETH"

    assert losers[0]["symbol"] == "ETH"
    assert losers[1]["symbol"] == "BTC"

    # Test update
    now2 = datetime.now(timezone.utc)
    items2 = [
        {
            "symbol": "BTC",
            "price_change_percent": -10.0,
            "last_price": 50000.0,
            "volume": 2000.0,
            "updated_at": now2,
        }
    ]
    await binance_repo.upsert_many(items2)
    gainers, losers = await binance_repo.get_gainers_losers(limit=10)
    assert len(gainers) == 2

    assert gainers[0]["symbol"] == "ETH"
    assert gainers[1]["symbol"] == "BTC"

    assert gainers[1]["last_price"] == 50000.0
    assert gainers[1]["volume"] == 2000.0


@pytest.mark.asyncio
async def test_get_gainers_losers_endpoint(monkeypatch, async_client):
    import app.api.main as app_main
    app_main.app.state.API_KEY = "dev-secret-key"

    # Mock the repo
    mock_gainers = [
        {"symbol": "BTC", "price_change_percent": 5.0, "last_price": 60000.0, "volume": 1000.0, "updated_at": "2023-01-01T00:00:00Z"},
    ]
    mock_losers = [
        {"symbol": "ETH", "price_change_percent": -2.0, "last_price": 3000.0, "volume": 5000.0, "updated_at": "2023-01-01T00:00:00Z"},
    ]

    async def mock_get_gainers_losers(limit=10):
        return mock_gainers, mock_losers

    # The router imports the singleton BINANCE_TICKER_REPO from app.api.main
    # Let's set the mock attribute on that instance
    import app.api.main
    monkeypatch.setattr(app.api.main.BINANCE_TICKER_REPO, "get_gainers_losers", mock_get_gainers_losers)

    response = await async_client.get("/api/binance/gainers-losers", headers={"X-API-Key": "dev-secret-key"})
    assert response.status_code == 200
    data = response.json()
    assert "gainers" in data
    assert "losers" in data
    assert len(data["gainers"]) == 1
    assert data["gainers"][0]["symbol"] == "BTC"
    assert data["losers"][0]["symbol"] == "ETH"
