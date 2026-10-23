from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import app.services.analyst_service as analyst_service
from app.services.analyst_service import (
    get_analyst_activity,
    summarize_actions,
    summarize_estimates,
    summarize_recommendations,
)

HEADERS = {"X-API-Key": "test-api-key"}


@pytest.fixture(autouse=True)
def _reset_cache():
    analyst_service._reset_cache_for_tests()
    yield
    analyst_service._reset_cache_for_tests()


def _upgrades_downgrades():
    frame = pd.DataFrame(
        [
            {
                "GradeDate": datetime(2026, 10, 20, 8, 0),
                "Firm": "Morgan Stanley",
                "ToGrade": "Overweight",
                "FromGrade": "Equal-Weight",
                "Action": "up",
                "priceTargetAction": "Raises",
                "currentPriceTarget": 260.0,
                "priorPriceTarget": 200.0,
            },
            {
                "GradeDate": datetime(2026, 10, 1, 8, 0),
                "Firm": "UBS",
                "ToGrade": "Buy",
                "FromGrade": "Buy",
                "Action": "main",
                "priceTargetAction": "Lowers",
                "currentPriceTarget": 240.0,
                "priorPriceTarget": 250.0,
            },
            {
                "GradeDate": datetime(2026, 9, 15, 8, 0),
                "Firm": "Jefferies",
                "ToGrade": "Hold",
                "FromGrade": "Buy",
                "Action": "down",
                "priceTargetAction": "Lowers",
                "currentPriceTarget": 0.0,
                "priorPriceTarget": 0.0,
            },
            {
                "GradeDate": datetime(2025, 1, 1, 8, 0),
                "Firm": "Old Firm",
                "ToGrade": "Sell",
                "FromGrade": "",
                "Action": "init",
                "priceTargetAction": "Announces",
                "currentPriceTarget": 100.0,
                "priorPriceTarget": 0.0,
            },
        ]
    )
    return frame.set_index("GradeDate")


def _recommendations():
    return pd.DataFrame(
        [
            {"period": "0m", "strongBuy": 10, "buy": 20, "hold": 8, "sell": 2},
            {"period": "-1m", "strongBuy": 9, "buy": 18, "hold": 10, "sell": 3},
            {"period": "-2m", "strongBuy": 8, "buy": 16, "hold": 12, "sell": 4},
            {"period": "-3m", "strongBuy": 8, "buy": 14, "hold": 14, "sell": 4},
        ]
    ).assign(strongSell=0)


def _eps_trend():
    return pd.DataFrame(
        {
            "current": [1.10, 1.25, 4.40, 5.00],
            "7daysAgo": [1.10, 1.24, 4.38, 4.95],
            "30daysAgo": [1.05, 1.20, 4.20, 4.80],
            "60daysAgo": [1.00, 1.18, 4.10, 4.70],
            "90daysAgo": [1.00, 1.15, 4.00, 4.60],
        },
        index=pd.Index(["0q", "+1q", "0y", "+1y"], name="period"),
    )


def _eps_revisions():
    return pd.DataFrame(
        {
            "upLast7days": [1, 0, 2, 1],
            "upLast30days": [5, 3, 9, 6],
            "downLast30days": [0, 1, 1, 2],
            "downLast7Days": [0, 0, 0, 0],
        },
        index=pd.Index(["0q", "+1q", "0y", "+1y"], name="period"),
    )


def test_summarize_actions_counts_the_window():
    rows = analyst_service._records(_upgrades_downgrades())
    result = summarize_actions(rows, date(2026, 10, 23), days=90)

    assert (result["upgrades"], result["downgrades"]) == (1, 1)
    assert (result["target_raises"], result["target_cuts"]) == (1, 1)
    assert result["initiations"] == 0  # outside 90 days
    latest = result["recent_actions"][0]
    assert latest == {
        "date": "2026-10-20",
        "firm": "Morgan Stanley",
        "action": "upgrade",
        "from_grade": "Equal-Weight",
        "to_grade": "Overweight",
        "price_target": 260.0,
        "prior_price_target": 200.0,
        "target_change_percent": 30.0,
    }
    # A zero target means "none given", not a cut to $0.
    assert result["recent_actions"][2]["target_change_percent"] is None


def test_summarize_recommendations_compares_three_months():
    result = summarize_recommendations(analyst_service._records(_recommendations()))

    assert result["buy_percent"] == 75.0
    assert result["buy_percent_change_3m"] == 20.0
    assert result["three_months_ago"]["hold"] == 14
    assert summarize_recommendations([]) is None


def test_summarize_estimates_reads_revisions():
    result = summarize_estimates(
        analyst_service._records(_eps_trend()),
        analyst_service._records(_eps_revisions()),
    )

    assert result["direction"] == "rising"
    year = result["periods"]["0y"]
    assert year["eps_estimate"] == 4.40
    assert year["change_30d_percent"] == pytest.approx(4.76, abs=0.01)
    assert year["change_90d_percent"] == 10.0
    assert (year["up_30d"], year["down_30d"], year["down_7d"]) == (9, 1, 0)

    falling = _eps_trend()
    falling.loc["0y", "current"] = 4.0
    assert (
        summarize_estimates(analyst_service._records(falling), [])["direction"]
        == "falling"
    )
    assert summarize_estimates([], [])["direction"] is None


async def test_get_analyst_activity_combines_and_caches():
    ticker = MagicMock()
    ticker.upgrades_downgrades = _upgrades_downgrades()
    ticker.recommendations = _recommendations()
    ticker.eps_trend = _eps_trend()
    ticker.eps_revisions = _eps_revisions()

    with patch("yfinance.Ticker", return_value=ticker) as cls:
        result = await get_analyst_activity("nvda", days=365)
        again = await get_analyst_activity("NVDA", days=365)

    assert again == result
    cls.assert_called_once_with("NVDA")
    assert result["symbol"] == "NVDA"
    assert result["rating_changes"]["upgrades"] == 1
    assert result["recommendations"]["buy_percent"] == 75.0
    assert result["estimates"]["direction"] == "rising"


async def test_get_analyst_activity_none_when_yahoo_has_nothing():
    ticker = MagicMock()
    for name in ("upgrades_downgrades", "recommendations", "eps_trend"):
        setattr(ticker, name, pd.DataFrame())
    ticker.eps_revisions = None

    with patch("yfinance.Ticker", return_value=ticker):
        assert await get_analyst_activity("SPY") is None


async def test_analysts_api(async_client, monkeypatch):
    from app.api import research as research_api

    seen = []

    async def fake(symbol, days):
        seen.append((symbol, days))
        return {"symbol": symbol} if symbol == "NVDA" else None

    monkeypatch.setattr(research_api, "get_analyst_activity", fake)

    resp = await async_client.get(
        "/api/research/analysts",
        params={"symbol": "nvda", "days": 30},
        headers=HEADERS,
    )
    assert resp.json() == {"symbol": "NVDA"}
    assert seen == [("NVDA", 30)]
    resp = await async_client.get(
        "/api/research/analysts", params={"symbol": "SPY"}, headers=HEADERS
    )
    assert resp.status_code == 404
