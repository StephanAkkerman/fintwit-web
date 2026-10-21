from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

import app.services.fundamentals_service as fundamentals_service
from app.api import research as research_api
from app.services.fundamentals_service import get_valuation
from app.services.price_context import summarize_trend

HEADERS = {"X-API-Key": "test-api-key"}


@pytest.fixture(autouse=True)
def _reset_cache():
    fundamentals_service._reset_cache_for_tests()
    yield
    fundamentals_service._reset_cache_for_tests()


async def test_valuation_maps_analysts_and_short_interest():
    ticker = MagicMock()
    ticker.info = {
        "longName": "Apple Inc.",
        "sector": "Technology",
        "currentPrice": 250.0,
        "forwardPE": 30.0,
        "targetMeanPrice": 275.0,
        "targetHighPrice": 320.0,
        "recommendationKey": "buy",
        "recommendationMean": 1.9,
        "numberOfAnalystOpinions": 41,
        "shortPercentOfFloat": 0.0071,
        "shortRatio": 1.4,
        "revenueGrowth": 0.08,
        "beta": float("nan"),
    }
    with patch("yfinance.Ticker", return_value=ticker):
        result = await get_valuation("aapl")
        again = await get_valuation("AAPL")

    assert again == result  # cached
    assert result["symbol"] == "AAPL"
    assert result["name"] == "Apple Inc."
    assert result["fundamentals"] == {"forward_pe": 30.0}
    assert result["analysts"] == {
        "rating": "buy",
        "rating_score": 1.9,
        "analyst_count": 41,
        "target_mean": 275.0,
        "target_high": 320.0,
        "upside_percent": 10.0,
    }
    assert result["short_interest"] == {
        "short_percent_of_float": 0.71,
        "short_ratio_days": 1.4,
    }
    # NaN beta dropped; ratios turned into percent.
    assert result["valuation"] == {"price": 250.0, "revenue_growth_percent": 8.0}


async def test_valuation_returns_none_without_info():
    ticker = MagicMock()
    ticker.info = {}
    with patch("yfinance.Ticker", return_value=ticker):
        assert await get_valuation("NOPE") is None


def _series(closes: list[float], end: date = date(2026, 10, 9)) -> list[dict]:
    start = end - timedelta(days=len(closes) - 1)
    return [
        {"t": (start + timedelta(days=i)).isoformat(), "close": c}
        for i, c in enumerate(closes)
    ]


def test_trend_from_a_rising_year():
    points = _series([100.0 + i * 0.5 for i in range(366)])
    trend = summarize_trend(points)

    assert trend["last_close"] == 282.5
    assert trend["returns_percent"]["1y"] == pytest.approx(182.5, abs=0.1)
    assert trend["returns_percent"]["1m"] == pytest.approx(5.6, abs=0.1)
    assert trend["sma_50"]["price_vs_percent"] > 0
    assert trend["sma_200"]["value"] < trend["sma_50"]["value"]
    assert trend["trend"] == "uptrend"


def test_trend_skips_windows_longer_than_the_history():
    trend = summarize_trend(_series([10.0, 9.0, 8.0] * 20))

    assert trend["returns_percent"]["1m"] is not None
    assert trend["returns_percent"]["3m"] is None
    assert trend["returns_percent"]["1y"] is None
    assert "sma_50" in trend and "sma_200" not in trend
    assert trend["trend"] is None
    assert summarize_trend([]) is None


async def test_research_api(async_client, monkeypatch):
    async def valuation(symbol):
        return {"symbol": symbol} if symbol == "NVDA" else None

    async def technicals(symbol, hint):
        return {"symbol": symbol, "hint": hint}

    async def context(symbol):
        return None

    async def indicators(symbol, kind):
        return None

    monkeypatch.setattr(research_api, "get_symbol_indicators", indicators)
    monkeypatch.setattr(research_api, "get_valuation", valuation)
    monkeypatch.setattr(research_api, "get_tradingview_ta_summary", technicals)
    monkeypatch.setattr(research_api, "get_price_context", context)

    resp = await async_client.get(
        "/api/research/valuation", params={"symbol": " nvda "}, headers=HEADERS
    )
    assert resp.json() == {"symbol": "NVDA"}
    resp = await async_client.get(
        "/api/research/valuation", params={"symbol": "XYZ"}, headers=HEADERS
    )
    assert resp.status_code == 404

    resp = await async_client.get(
        "/api/research/technicals",
        params={"symbol": "btc", "asset_kind": "crypto"},
        headers=HEADERS,
    )
    assert resp.json() == {"symbol": "BTC", "hint": "crypto", "indicators": None}
    resp = await async_client.get(
        "/api/research/technicals",
        params={"symbol": "btc", "asset_kind": "nft"},
        headers=HEADERS,
    )
    assert resp.status_code == 422

    resp = await async_client.get(
        "/api/research/price-context", params={"symbol": "NVDA"}, headers=HEADERS
    )
    assert resp.status_code == 404
    resp = await async_client.get(
        "/api/research/price-context", params={"symbol": "NVDA"}
    )
    assert resp.status_code == 401


async def test_technicals_falls_back_to_indicators(async_client, monkeypatch):
    async def no_summary(symbol, hint):
        return None

    async def indicators(symbol, kind):
        return {"symbol": symbol, "rsi": {"value": 66.6}}

    monkeypatch.setattr(research_api, "get_tradingview_ta_summary", no_summary)
    monkeypatch.setattr(research_api, "get_symbol_indicators", indicators)

    resp = await async_client.get(
        "/api/research/technicals",
        params={"symbol": "ewz", "asset_kind": "etf"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "symbol": "EWZ",
        "indicators": {"symbol": "EWZ", "rsi": {"value": 66.6}},
    }


async def test_indicators_api(async_client, monkeypatch):
    seen = []

    async def indicators(symbols, kind):
        seen.append((symbols, kind))
        return {s: None for s in symbols}

    monkeypatch.setattr(research_api, "get_indicators", indicators)

    resp = await async_client.get(
        "/api/research/indicators",
        params={"symbols": "aapl, ewz,AAPL,,", "asset_kind": "etf"},
        headers=HEADERS,
    )
    assert resp.json() == {"AAPL": None, "EWZ": None}
    assert seen == [(["AAPL", "EWZ"], "etf")]

    too_many = ",".join(f"T{i}" for i in range(51))
    resp = await async_client.get(
        "/api/research/indicators", params={"symbols": too_many}, headers=HEADERS
    )
    assert resp.status_code == 422
    resp = await async_client.get(
        "/api/research/indicators", params={"symbols": " , "}, headers=HEADERS
    )
    assert resp.status_code == 422
