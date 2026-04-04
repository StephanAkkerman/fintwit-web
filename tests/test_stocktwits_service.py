from unittest.mock import AsyncMock

import pytest

from app.services.stocktwits_service import get_stocktwits_data


class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.mark.asyncio
async def test_get_stocktwits_data_formats_happy_path(monkeypatch):
    from app.services import stocktwits_service as svc

    svc._CACHE.clear()

    async def _no_curl(_url: str):
        return None

    monkeypatch.setattr("app.services.stocktwits_service._fetch_with_curl", _no_curl)

    payload = {
        "table": {
            "ts": [
                {"stock_id": 1, "val": "100", "price": "10", "change": "5"},
                {"stock_id": 2, "val": "50", "price": "20", "change": "-1"},
            ]
        },
        "stocks": {
            "1": {"symbol": "AAPL", "name": "Apple Inc."},
            "2": {"symbol": "TSLA", "name": "Tesla Inc."},
        },
    }
    client = AsyncMock()
    client.get = AsyncMock(return_value=_FakeResponse(200, payload))

    data = await get_stocktwits_data(client, "ts")

    assert data is not None
    assert len(data) == 2
    assert data[0]["symbol"] == "AAPL"
    assert data[1]["symbol"] == "TSLA"


@pytest.mark.asyncio
async def test_get_stocktwits_data_uses_curl_fallback_when_blocked(monkeypatch):
    from app.services import stocktwits_service as svc

    svc._CACHE.clear()

    blocked = _FakeResponse(403, ValueError("not json"))
    client = AsyncMock()
    client.get = AsyncMock(return_value=blocked)

    payload = {
        "table": {"ts": [{"stock_id": 1, "val": "100", "price": "10", "change": "5"}]},
        "stocks": {"1": {"symbol": "AAPL", "name": "Apple Inc."}},
    }

    async def _fake_curl(_url: str):
        return payload

    monkeypatch.setattr("app.services.stocktwits_service._fetch_with_curl", _fake_curl)

    data = await get_stocktwits_data(client, "ts")

    assert data is not None
    assert len(data) == 1
    assert data[0]["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_get_stocktwits_data_invalid_keyword_returns_none():
    from app.services import stocktwits_service as svc

    svc._CACHE.clear()

    client = AsyncMock()

    data = await get_stocktwits_data(client, "invalid")

    assert data is None


@pytest.mark.asyncio
async def test_get_stocktwits_data_returns_cached_when_upstream_temporarily_fails(
    monkeypatch,
):
    from app.services import stocktwits_service as svc

    svc._CACHE.clear()
    client = AsyncMock()

    payload = {
        "table": {"ts": [{"stock_id": 1, "val": "100", "price": "10", "change": "5"}]},
        "stocks": {"1": {"symbol": "AAPL", "name": "Apple Inc."}},
    }

    state = {"count": 0}

    async def _fake_curl(_url: str):
        state["count"] += 1
        if state["count"] == 1:
            return payload
        return None

    blocked = _FakeResponse(403, ValueError("not json"))
    client.get = AsyncMock(return_value=blocked)
    monkeypatch.setattr("app.services.stocktwits_service._fetch_with_curl", _fake_curl)

    first = await svc.get_stocktwits_data(client, "ts")
    second = await svc.get_stocktwits_data(client, "ts")

    assert first is not None
    assert second is not None
    assert first == second
    assert second[0]["symbol"] == "AAPL"
