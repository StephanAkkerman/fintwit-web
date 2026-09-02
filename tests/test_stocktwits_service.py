from unittest.mock import AsyncMock, patch

import pytest

from app.services.stocktwits_service import (
    get_stocktwits_data,
    get_stocktwits_sentiment,
)


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


# ---------------------------------------------------------------------------
# get_stocktwits_sentiment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stocktwits_sentiment_empty_symbol_returns_none():
    from app.services import stocktwits_service as svc

    svc._SENTIMENT_CACHE.clear()

    assert await get_stocktwits_sentiment("") is None


@pytest.mark.asyncio
async def test_get_stocktwits_sentiment_parses_bullish_bearish_percent(monkeypatch):
    from app.services import stocktwits_service as svc

    svc._SENTIMENT_CACHE.clear()

    payload = {"symbol": "VELO", "bullish_percent": 62.5, "bearish_percent": 37.5}

    async def _fake_curl(_url: str):
        return payload

    monkeypatch.setattr("app.services.stocktwits_service._fetch_with_curl", _fake_curl)

    result = await get_stocktwits_sentiment("velo")

    assert result == {
        "source": "stocktwits",
        "symbol": "VELO",
        "bullish_percent": 62.5,
        "bearish_percent": 37.5,
        "message_volume": None,
        "as_of": None,
        "website": "https://stocktwits.com/symbol/VELO",
    }


@pytest.mark.asyncio
async def test_get_stocktwits_sentiment_derives_percent_from_counts(monkeypatch):
    from app.services import stocktwits_service as svc

    svc._SENTIMENT_CACHE.clear()

    payload = {"bullish_count": 30, "bearish_count": 10, "volume": 40}

    async def _fake_curl(_url: str):
        return payload

    monkeypatch.setattr("app.services.stocktwits_service._fetch_with_curl", _fake_curl)

    result = await get_stocktwits_sentiment("AAPL")

    assert result["bullish_percent"] == 75.0
    assert result["bearish_percent"] == 25.0
    assert result["message_volume"] == 40


@pytest.mark.asyncio
async def test_get_stocktwits_sentiment_derives_percent_from_score(monkeypatch):
    from app.services import stocktwits_service as svc

    svc._SENTIMENT_CACHE.clear()

    payload = {"sentiment_score": 20}

    async def _fake_curl(_url: str):
        return payload

    monkeypatch.setattr("app.services.stocktwits_service._fetch_with_curl", _fake_curl)

    result = await get_stocktwits_sentiment("AAPL")

    assert result["bullish_percent"] == 60.0
    assert result["bearish_percent"] == 40.0


@pytest.mark.asyncio
async def test_get_stocktwits_sentiment_uses_last_point_in_series(monkeypatch):
    from app.services import stocktwits_service as svc

    svc._SENTIMENT_CACHE.clear()

    payload = {
        "data": [
            {"bullish_percent": 40.0, "bearish_percent": 60.0},
            {"bullish_percent": 80.0, "bearish_percent": 20.0},
        ]
    }

    async def _fake_curl(_url: str):
        return payload

    monkeypatch.setattr("app.services.stocktwits_service._fetch_with_curl", _fake_curl)

    result = await get_stocktwits_sentiment("AAPL")

    assert result["bullish_percent"] == 80.0
    assert result["bearish_percent"] == 20.0


@pytest.mark.asyncio
async def test_get_stocktwits_sentiment_returns_none_for_unrecognized_payload(
    monkeypatch,
):
    from app.services import stocktwits_service as svc

    svc._SENTIMENT_CACHE.clear()

    async def _fake_curl(_url: str):
        return {"unrelated": "field"}

    monkeypatch.setattr("app.services.stocktwits_service._fetch_with_curl", _fake_curl)

    assert await get_stocktwits_sentiment("AAPL") is None


@pytest.mark.asyncio
async def test_get_stocktwits_sentiment_falls_back_to_httpx_when_curl_blocked(
    monkeypatch,
):
    from app.services import stocktwits_service as svc

    svc._SENTIMENT_CACHE.clear()

    async def _no_curl(_url: str):
        return None

    monkeypatch.setattr("app.services.stocktwits_service._fetch_with_curl", _no_curl)

    fake_client = AsyncMock()
    fake_client.get = AsyncMock(
        return_value=_FakeResponse(
            200, {"bullish_percent": 55.0, "bearish_percent": 45.0}
        )
    )
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=fake_client):
        result = await get_stocktwits_sentiment("AAPL")

    assert result["bullish_percent"] == 55.0


@pytest.mark.asyncio
async def test_get_stocktwits_sentiment_returns_cached_when_upstream_temporarily_fails(
    monkeypatch,
):
    from app.services import stocktwits_service as svc

    svc._SENTIMENT_CACHE.clear()

    state = {"count": 0}
    payload = {"bullish_percent": 70.0, "bearish_percent": 30.0}

    async def _fake_curl(_url: str):
        state["count"] += 1
        if state["count"] == 1:
            return payload
        return None

    monkeypatch.setattr("app.services.stocktwits_service._fetch_with_curl", _fake_curl)

    blocked_client = AsyncMock()
    blocked_client.get = AsyncMock(
        return_value=_FakeResponse(403, ValueError("not json"))
    )
    blocked_client.__aenter__ = AsyncMock(return_value=blocked_client)
    blocked_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=blocked_client):
        first = await get_stocktwits_sentiment("AAPL")
        second = await get_stocktwits_sentiment("AAPL")

    assert first is not None
    assert second == first
