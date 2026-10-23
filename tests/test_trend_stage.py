from datetime import date, timedelta

import pytest

import app.services.trend_stage as trend_stage
from app.services.trend_stage import (
    relative_strength,
    sector_etf,
    stage_analysis,
)

HEADERS = {"X-API-Key": "test-api-key"}


def _weekly(closes, start=date(2025, 1, 6)):
    return [
        {"t": (start + timedelta(weeks=i)).isoformat(), "close": close}
        for i, close in enumerate(closes)
    ]


def test_steady_advance_is_stage_two():
    result = stage_analysis(_weekly([100 + i for i in range(60)]))

    assert result["stage"] == 2
    assert result["name"] == "advancing"
    assert result["price_vs_ma30w_percent"] > 0
    assert result["ma30w_slope_5w_percent"] > 1
    # Every week since the average had 35 weeks to form was an advance.
    assert result["weeks_in_stage"] == 60 - 35 + 1
    assert result["previous_stage"] is None


def test_decline_is_stage_four_and_a_flat_floor_after_it_a_base():
    declining = [200 - 2 * i for i in range(50)]
    assert stage_analysis(_weekly(declining))["stage"] == 4

    based = declining + [102, 98] * 20
    result = stage_analysis(_weekly(based))
    assert result["stage"] == 1
    assert result["name"] == "basing"
    assert result["previous_stage"] == 4


def test_flat_after_an_advance_is_a_top():
    closes = [100 + 2 * i for i in range(50)] + [200, 196] * 20
    result = stage_analysis(_weekly(closes))

    assert result["stage"] == 3
    assert result["previous_stage"] == 2


def test_a_dip_just_under_a_rising_average_stays_stage_two():
    history = [100 + i for i in range(59)]

    def closing_at(fraction):
        # The close that sits ``fraction`` of the way to the average it is in.
        return fraction * sum(history[-29:]) / (30 - fraction)

    dip = stage_analysis(_weekly(history + [closing_at(0.99)]))
    assert dip["price_vs_ma30w_percent"] == pytest.approx(-1, abs=0.01)
    assert dip["stage"] == 2

    # A real break of the average.
    assert stage_analysis(_weekly(history + [closing_at(0.85)]))["stage"] == 3


def test_too_little_history():
    assert stage_analysis(_weekly([100] * 30)) is None


def test_relative_strength_against_a_benchmark():
    closes = [100.0] * 50 + [100 + 5 * i for i in range(1, 11)]
    stock = _weekly(closes)
    flat = _weekly([100.0] * 60)

    result = relative_strength(stock, flat)
    assert result["mansfield"] > 0
    assert result["mansfield_rising_4w"] is True
    assert result["outperformance_13w_pp"] == pytest.approx(50.0)

    # Matched by ISO week, so a mid-week date for the running bar still pairs.
    shifted = flat[:-1] + [{"t": "2026-02-18", "close": 100.0}]
    stock[-1]["t"] = "2026-02-16"
    assert relative_strength(stock, shifted)["mansfield"] == result["mansfield"]

    assert relative_strength(stock[:10], flat) is None


def test_sector_etf_accepts_yahoo_and_gics_names():
    assert sector_etf("Healthcare") == "XLV"
    assert sector_etf("Health Care") == "XLV"
    assert sector_etf("Financial Services") == "XLF"
    assert sector_etf(None) is None
    assert sector_etf("Shell Companies") is None


async def test_get_trend_stage_reads_stock_market_and_sector(monkeypatch):
    series = {
        "AAPL": _weekly([100 + i for i in range(60)]),
        "SPY": _weekly([100.0] * 60),
        "XLK": _weekly([100 + 0.5 * i for i in range(60)]),
    }
    fetched = []

    async def price_series(symbol, range_key):
        fetched.append((symbol, range_key))
        return series.get(symbol, [])

    async def valuation(symbol):
        return {"sector": "Technology"}

    monkeypatch.setattr(trend_stage, "get_price_series", price_series)
    monkeypatch.setattr(trend_stage, "get_valuation", valuation)

    result = await trend_stage.get_trend_stage("aapl")

    assert result["symbol"] == "AAPL"
    assert result["stage"]["stage"] == 2
    assert result["vs_market"]["mansfield"] > 0
    assert result["sector"]["etf"] == "XLK"
    assert result["sector"]["stage"]["stage"] == 2
    assert result["sector"]["stock_vs_sector"]["mansfield"] > 0
    assert ("XLK", "5Y") in fetched

    assert await trend_stage.get_trend_stage("NEW") is None


async def test_trend_stage_api(async_client, monkeypatch):
    from app.api import research as research_api

    async def fake(symbol):
        return {"symbol": symbol} if symbol == "AAPL" else None

    monkeypatch.setattr(research_api, "get_trend_stage", fake)

    resp = await async_client.get(
        "/api/research/trend-stage", params={"symbol": "aapl"}, headers=HEADERS
    )
    assert resp.json() == {"symbol": "AAPL"}
    resp = await async_client.get(
        "/api/research/trend-stage", params={"symbol": "NEW"}, headers=HEADERS
    )
    assert resp.status_code == 404
