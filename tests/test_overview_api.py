import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch("app.api.main.run_stream", new_callable=AsyncMock):
        from app.api.main import app

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def test_mention_heat_returns_list(client):
    resp = client.get("/api/overview/mention-heat")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_mention_heat_min_mentions_param(client):
    resp = client.get("/api/overview/mention-heat?min_mentions=200")
    assert resp.status_code == 200


def test_sentiment_shift_returns_list(client):
    resp = client.get("/api/overview/sentiment-shift")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_volume_baseline_returns_list(client):
    resp = client.get("/api/overview/volume-baseline")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_sector_mentions_returns_list(client):
    resp = client.get("/api/overview/sector-mentions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_hidden_gems_returns_list(client):
    resp = client.get("/api/overview/hidden-gems")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_mention_frequency_returns_scopes(client):
    resp = client.post(
        "/api/overview/mention-frequency",
        json={"requests": [{"author": "someone", "tickers": ["NVDA"]}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "personal" in body and "global" in body


def test_mention_frequency_empty(client):
    resp = client.post("/api/overview/mention-frequency", json={"requests": []})
    assert resp.status_code == 200
    assert resp.json() == {"personal": {}, "global": {}}


def test_ticker_timeseries_returns_shape(client):
    resp = client.get("/api/overview/ticker-timeseries?ticker=AAPL&window_hours=24")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert isinstance(body["points"], list)
    assert "summary" in body
    assert "total_mentions" in body["summary"]


def test_ticker_timeseries_requires_ticker(client):
    resp = client.get("/api/overview/ticker-timeseries")
    assert resp.status_code == 422


def test_ticker_timeseries_rejects_blank_ticker(client):
    resp = client.get("/api/overview/ticker-timeseries?ticker=%20%20")
    assert resp.status_code == 422


def test_macro_strip_returns_list(client):
    mock_quote = {"price": 5000.0, "change_percent": 0.5}
    with patch(
        "app.api.overview.get_tradingview_quote",
        new_callable=AsyncMock,
        return_value=mock_quote,
    ):
        resp = client.get("/api/overview/macro-strip")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if data:
        assert "label" in data[0]
        assert "price" in data[0]
        assert "change_pct" in data[0]
        assert "sparkline" in data[0]
