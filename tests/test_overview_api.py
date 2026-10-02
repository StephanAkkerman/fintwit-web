import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch("app.api.main.run_stream", new_callable=AsyncMock):
        from app.api.main import app

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


@pytest.fixture(autouse=True)
def _reset_strip_cache():
    import app.api.overview as overview

    overview._strip_cache = None
    overview._ticker_history_cache.clear()
    overview._trend_cache.clear()
    yield
    overview._strip_cache = None
    overview._ticker_history_cache.clear()
    overview._trend_cache.clear()


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


def test_trend_summary_returns_object(client):
    resp = client.get("/api/overview/trend-summary?window=30d")
    assert resp.status_code == 200
    body = resp.json()
    assert body["window"] == "30d"
    assert len(body["buckets"]) == 30
    assert isinstance(body["tickers"], list)


def test_trend_summary_rejects_unknown_window(client):
    resp = client.get("/api/overview/trend-summary?window=2d")
    assert resp.status_code == 422


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


def test_ticker_price_history_returns_points(client):
    mock_history = [
        {"t": "2024-01-01T14:30:00+00:00", "close": 184.0, "high": 184.5, "low": 183.5},
        {"t": "2024-01-01T14:35:00+00:00", "close": 185.0, "high": 185.5, "low": 184.0},
    ]
    with patch(
        "app.api.overview.get_price_history",
        new_callable=AsyncMock,
        return_value=mock_history,
    ) as mock_get:
        resp = client.get("/api/overview/ticker-price-history?ticker=aapl")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert body["points"] == mock_history
    # Plain symbol resolved on the first attempt: no crypto "-USD" fallback needed.
    mock_get.assert_awaited_once_with("AAPL", range_="1d", interval="5m")


def test_ticker_price_history_falls_back_to_usd_symbol(client):
    mock_history = [
        {
            "t": "2024-01-01T14:30:00+00:00",
            "close": 96000.0,
            "high": 96500.0,
            "low": 95500.0,
        },
    ]

    async def fake_get_price_history(symbol, *, range_, interval):
        if symbol == "BTC-USD":
            return mock_history
        return None

    with patch(
        "app.api.overview.get_price_history", side_effect=fake_get_price_history
    ):
        resp = client.get("/api/overview/ticker-price-history?ticker=BTC")

    assert resp.status_code == 200
    assert resp.json()["points"] == mock_history


def test_ticker_price_history_prefers_crypto_for_etf_lookalikes(client):
    # "BTC" and "NEAR" are real Yahoo ETFs; the bare symbol must not win.
    calls = []

    async def fake_get_price_history(symbol, *, range_, interval):
        calls.append(symbol)
        return [{"t": "t", "close": 1.0, "high": 1.0, "low": 1.0}]

    with patch(
        "app.api.overview.get_price_history", side_effect=fake_get_price_history
    ):
        for ticker in ("BTC", "NEAR"):
            resp = client.get(f"/api/overview/ticker-price-history?ticker={ticker}")
            assert resp.status_code == 200

    assert calls == ["BTC-USD", "NEAR-USD"]


def test_ticker_price_history_empty_when_unresolvable(client):
    with patch(
        "app.api.overview.get_price_history",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = client.get("/api/overview/ticker-price-history?ticker=NOTREAL")

    assert resp.status_code == 200
    assert resp.json() == {"ticker": "NOTREAL", "points": []}


def test_ticker_price_history_requires_ticker(client):
    resp = client.get("/api/overview/ticker-price-history")
    assert resp.status_code == 422


def test_ticker_price_history_is_cached(client):
    mock_history = [
        {"t": "2024-01-01T14:30:00+00:00", "close": 184.0, "high": 184.5, "low": 183.5},
    ]
    with patch(
        "app.api.overview.get_price_history",
        new_callable=AsyncMock,
        return_value=mock_history,
    ) as mock_get:
        client.get("/api/overview/ticker-price-history?ticker=AAPL")
        client.get("/api/overview/ticker-price-history?ticker=AAPL")

    mock_get.assert_awaited_once()


def test_macro_strip_returns_list(client):
    mock_quote = {"price": 5000.0, "change_percent": 0.5}
    mock_history = [
        {
            "t": "2024-01-01T00:00:00+00:00",
            "close": 4990.0,
            "high": 4995.0,
            "low": 4985.0,
        },
        {
            "t": "2024-01-01T00:05:00+00:00",
            "close": 5000.0,
            "high": 5002.0,
            "low": 4995.0,
        },
    ]
    with (
        patch(
            "app.api.overview.get_tradingview_quote",
            new_callable=AsyncMock,
            return_value=mock_quote,
        ),
        patch(
            "app.api.overview.get_price_history",
            new_callable=AsyncMock,
            return_value=mock_history,
        ),
    ):
        resp = client.get("/api/overview/macro-strip")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 7
    if data:
        assert "label" in data[0]
        assert "price" in data[0]
        assert "change_pct" in data[0]
        assert "sparkline" in data[0]

    for item in data:
        assert item["sparkline"] == [4990.0, 5000.0]


def test_macro_strip_sparkline_empty_when_history_unavailable(client):
    mock_quote = {"price": 5000.0, "change_percent": 0.5}
    with (
        patch(
            "app.api.overview.get_tradingview_quote",
            new_callable=AsyncMock,
            return_value=mock_quote,
        ),
        patch(
            "app.api.overview.get_price_history",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        resp = client.get("/api/overview/macro-strip")
    assert resp.status_code == 200
    data = resp.json()
    assert all(item["sparkline"] == [] for item in data)


def test_macro_strip_tile_survives_history_exception(client):
    mock_quote = {"price": 5000.0, "change_percent": 0.5}
    with (
        patch(
            "app.api.overview.get_tradingview_quote",
            new_callable=AsyncMock,
            return_value=mock_quote,
        ),
        patch(
            "app.api.overview.get_price_history",
            new_callable=AsyncMock,
            side_effect=Exception("yahoo down"),
        ),
    ):
        resp = client.get("/api/overview/macro-strip")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 7
    assert all(item["sparkline"] == [] for item in data)


def test_activity_summary_returns_shape(client):
    resp = client.get("/api/overview/activity-summary?window_hours=24")
    assert resp.status_code == 200
    data = resp.json()
    assert data["window_hours"] == 24
    assert set(data["tweets"]) == {"current", "previous"}
    assert set(data["authors"]) == {"current", "previous"}
    assert "bull_pct" in data["sentiment"]
    assert "top_ticker" in data
    assert "top_mover" in data
