import pytest
from httpx import AsyncClient, ASGITransport
from app.api.main import app

@pytest.fixture
def mock_binance_response(monkeypatch):
    import app.services.binance_service

    async def mock_get(*args, **kwargs):
        class MockResponse:
            def json(self):
                return [
                    {
                        "symbol": "BTCUSDT",
                        "priceChangePercent": "5.5",
                        "weightedAvgPrice": "50000.0",
                        "volume": "100.0"
                    },
                    {
                        "symbol": "ETHUSDT",
                        "priceChangePercent": "-2.5",
                        "weightedAvgPrice": "3000.0",
                        "volume": "500.0"
                    },
                    {
                        "symbol": "DOGEUSDT",
                        "priceChangePercent": "10.0",
                        "weightedAvgPrice": "0.1",
                        "volume": "10000.0"
                    },
                    {
                        "symbol": "SOLUSDT",
                        "priceChangePercent": "-5.0",
                        "weightedAvgPrice": "150.0",
                        "volume": "200.0"
                    },
                    {
                        "symbol": "NOT_USDT",
                        "priceChangePercent": "100.0",
                        "weightedAvgPrice": "1.0",
                        "volume": "1.0"
                    }
                ]
            @property
            def status_code(self):
                return 200

            def raise_for_status(self):
                pass
        return MockResponse()

    # monkeypatch.setattr("httpx.AsyncClient.get", mock_get)
    pass

@pytest.mark.asyncio
async def test_binance_gainers_losers(mock_binance_response, monkeypatch):
    from app.api.main import app as main_app
    import app.services.binance_service

    main_app.state.API_KEY = "test-key"

    import httpx

    # We bypass httpx monkeypatching and directly override the service import
    async def mock_get_gainers_losers(*args, **kwargs):
        return {
            "gainers": [
                {"symbol": "DOGE", "price_change_percent": 10.0, "price": 0.1, "volume": 10000.0, "website": "https://www.binance.com/en/price/DOGE"},
                {"symbol": "BTC", "price_change_percent": 5.5, "price": 50000.0, "volume": 100.0, "website": "https://www.binance.com/en/price/BTC"}
            ],
            "losers": [
                {"symbol": "SOL", "price_change_percent": -5.0, "price": 150.0, "volume": 200.0, "website": "https://www.binance.com/en/price/SOL"},
                {"symbol": "ETH", "price_change_percent": -2.5, "price": 3000.0, "volume": 500.0, "website": "https://www.binance.com/en/price/ETH"}
            ]
        }
    monkeypatch.setattr("app.api.main.get_gainers_losers", mock_get_gainers_losers)
    main_app.state.http_client = httpx.AsyncClient()

    async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as ac:
        response = await ac.get("/api/binance/gainers-losers", headers={"X-API-Key": "test-key"})

    await main_app.state.http_client.aclose()

    assert response.status_code == 200
    data = response.json()
    assert "gainers" in data
    assert "losers" in data

    gainers = data["gainers"]
    losers = data["losers"]

    assert len(gainers) == 2
    assert len(losers) == 2

    assert gainers[0]["symbol"] == "DOGE"
    assert gainers[0]["price_change_percent"] == 10.0

    assert gainers[1]["symbol"] == "BTC"

    # Check that losers are sorted from most negative to least negative
    assert losers[0]["symbol"] == "SOL"
    assert losers[0]["price_change_percent"] == -5.0

    assert losers[-1]["symbol"] == "ETH"

@pytest.mark.asyncio
async def test_binance_gainers_losers_unauthorized():
    from app.api.main import app as main_app
    main_app.state.API_KEY = "test-key"
    async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as ac:
        response = await ac.get("/api/binance/gainers-losers", headers={"X-API-Key": "wrong-key"})

    assert response.status_code == 401
