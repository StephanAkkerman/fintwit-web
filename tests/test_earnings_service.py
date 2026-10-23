import time
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services import earnings_service


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    earnings_service._reset_cache_for_tests()
    monkeypatch.setattr(earnings_service, "_RETRY_DELAY_SECONDS", 0)
    yield
    earnings_service._reset_cache_for_tests()


def _response(status_code=200, json_data=None):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data
    return response


def _row(symbol):
    return {"symbol": symbol, "name": symbol, "time": "time-pre-market"}


@pytest.mark.asyncio
async def test_get_earnings_calendar_parses_rows():
    day0 = date.today().isoformat()
    day1 = (date.today() + timedelta(days=1)).isoformat()

    payload_day0 = {
        "data": {
            "rows": [
                {
                    "symbol": "aapl",
                    "name": "Apple Inc. Common Stock",
                    "marketCap": "3011000000000",
                    "fiscalQuarterEnding": "Sep/2026",
                    "epsForecast": "1.25",
                    "noOfEsts": "12",
                    "lastYearRptDt": "08/01/2025",
                    "lastYearEPS": "1.10",
                    "time": "time-after-hours",
                },
                {
                    "symbol": "",  # invalid row, should be dropped
                    "name": "No Symbol",
                    "time": "time-pre-market",
                },
            ]
        }
    }
    payload_day1 = {"data": {"rows": []}}

    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.side_effect = [
        _response(json_data=payload_day0),
        _response(json_data=payload_day1),
    ]

    result = await earnings_service.get_earnings_calendar(client, days=2)

    assert result is not None
    assert result["start_date"] == day0
    assert result["end_date"] == day1
    assert result["source"] == "nasdaq"
    assert len(result["days"]) == 2

    first_day = result["days"][0]
    assert first_day["date"] == day0
    assert first_day["count"] == 1
    row = first_day["rows"][0]
    assert row["symbol"] == "AAPL"
    assert row["name"] == "Apple Inc. Common Stock"
    assert row["session"] == "after-hours"
    assert row["session_emoji"] == "🌙"
    assert row["market_cap"] == 3_011_000_000_000.0
    assert row["eps_forecast"] == 1.25
    assert row["num_estimates"] == 12
    assert row["last_year_eps"] == 1.10
    assert (
        row["website"] == "https://www.nasdaq.com/market-activity/stocks/aapl/earnings"
    )

    second_day = result["days"][1]
    assert second_day["count"] == 0
    assert second_day["rows"] == []


@pytest.mark.asyncio
async def test_get_earnings_calendar_treats_missing_data_key_as_empty_not_failure():
    # A day with no "data"/"rows" key (typical for weekends) should still
    # count as a successful fetch with zero rows, not a service failure.
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.return_value = _response(json_data={"data": None, "message": None})

    result = await earnings_service.get_earnings_calendar(client, days=1)

    assert result is not None
    assert result["days"][0]["rows"] == []
    assert result["days"][0]["count"] == 0


@pytest.mark.asyncio
async def test_get_earnings_calendar_returns_none_when_every_day_fails():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.return_value = _response(status_code=503, json_data={})

    result = await earnings_service.get_earnings_calendar(client, days=3)

    assert result is None


@pytest.mark.asyncio
async def test_get_earnings_calendar_partial_failure_still_returns_payload():
    today = date.today().isoformat()

    async def get(url, params, headers):
        if params["date"] == today:
            return _response(status_code=500, json_data={})
        return _response(json_data={"data": {"rows": []}})

    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.side_effect = get

    result = await earnings_service.get_earnings_calendar(client, days=2)

    assert result is not None
    assert len(result["days"]) == 2
    # Today failed twice (request + retry): unknown, not "no earnings".
    assert result["failed_dates"] == [today]
    assert client.get.await_count == 3


@pytest.mark.asyncio
async def test_get_earnings_calendar_retries_a_failed_day_once():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.side_effect = [
        _response(status_code=503, json_data={}),
        _response(json_data={"data": {"rows": [_row("AAPL")]}}),
    ]

    result = await earnings_service.get_earnings_calendar(client, days=1)

    assert result["days"][0]["count"] == 1
    assert "failed_dates" not in result


@pytest.mark.asyncio
async def test_get_earnings_calendar_reuses_days_across_windows_and_stale_rows():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.return_value = _response(json_data={"data": {"rows": [_row("AAPL")]}})
    await earnings_service.get_earnings_calendar(client, days=3, limit_per_day=50)
    calls = client.get.await_count

    # A different window over the same days needs no new requests.
    result = await earnings_service.get_earnings_calendar(client, days=1)
    assert client.get.await_count == calls
    assert result["days"][0]["rows"][0]["symbol"] == "AAPL"

    # Once fresh data has expired, a failing Nasdaq gets the last good rows.
    earnings_service._CACHE.clear()
    expired = time.time() - 2 * earnings_service._CACHE_TTL_SECONDS
    for key, (_, rows) in list(earnings_service._DAY_CACHE.items()):
        earnings_service._DAY_CACHE[key] = (expired, rows)
    client.get.return_value = _response(status_code=503, json_data={})
    result = await earnings_service.get_earnings_calendar(client, days=1)
    assert result["days"][0]["rows"][0]["symbol"] == "AAPL"
    assert "failed_dates" not in result


@pytest.mark.asyncio
async def test_get_earnings_calendar_handles_request_error():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.side_effect = httpx.RequestError("boom")

    result = await earnings_service.get_earnings_calendar(client, days=1)

    assert result is None


@pytest.mark.asyncio
async def test_get_earnings_calendar_clamps_days_and_limit():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.return_value = _response(json_data={"data": {"rows": []}})

    result = await earnings_service.get_earnings_calendar(
        client, days=999, limit_per_day=-5
    )

    assert result is not None
    assert len(result["days"]) == 14  # clamped to max
    assert client.get.await_count == 14


@pytest.mark.asyncio
async def test_get_earnings_calendar_limits_rows_per_day():
    rows = [
        {"symbol": f"T{i}", "marketCap": str(1000 - i), "time": "time-not-supplied"}
        for i in range(5)
    ]
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.return_value = _response(json_data={"data": {"rows": rows}})

    result = await earnings_service.get_earnings_calendar(
        client, days=1, limit_per_day=2
    )

    assert result is not None
    day = result["days"][0]
    assert day["count"] == 5  # raw count preserved
    assert len(day["rows"]) == 2  # display list trimmed


@pytest.mark.asyncio
async def test_get_earnings_calendar_uses_cache_on_second_call():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.return_value = _response(json_data={"data": {"rows": []}})

    await earnings_service.get_earnings_calendar(client, days=1)
    await earnings_service.get_earnings_calendar(client, days=1)

    assert client.get.await_count == 1


@pytest.mark.parametrize(
    ("row", "surprise", "outcome"),
    [
        # Nasdaq's surprise is kept as-is.
        (
            {"eps_actual": 9.18, "eps_forecast": 7.07, "surprise_pct": 29.84},
            29.84,
            "beat",
        ),
        (
            {"eps_actual": 1.85, "eps_forecast": 1.93, "surprise_pct": -4.15},
            -4.15,
            "miss",
        ),
        (
            {"eps_actual": 1.16, "eps_forecast": 1.17, "surprise_pct": -0.85},
            -0.85,
            "inline",
        ),
        # Nasdaq sent "N/A": worked out from the consensus.
        (
            {"eps_actual": 0.44, "eps_forecast": 0.40, "surprise_pct": None},
            10.0,
            "beat",
        ),
        # A negative estimate: beating -0.50 with -0.25 is a positive surprise.
        (
            {"eps_actual": -0.25, "eps_forecast": -0.50, "surprise_pct": None},
            50.0,
            "beat",
        ),
        # Nothing to compare with.
        ({"eps_actual": 1.0, "eps_forecast": None, "surprise_pct": None}, None, None),
    ],
)
def test_classify_result(row, surprise, outcome):
    result = earnings_service.classify_result(row)
    assert result["surprise_pct"] == surprise
    assert result["outcome"] == outcome


def test_classify_result_without_actual_is_none():
    assert earnings_service.classify_result({"eps_actual": None}) is None


@pytest.mark.asyncio
async def test_get_earnings_results_keeps_reported_rows_over_weekdays():
    reported = {
        "data": {
            "rows": [
                {
                    "symbol": "TRV",
                    "name": "The Travelers Companies, Inc.",
                    "marketCap": "$80,069,861,000",
                    "epsForecast": "$7.07",
                    "eps": "$9.18",
                    "surprise": "29.84",
                    "time": "time-pre-market",
                },
                {"symbol": "LATE", "epsForecast": "$1.00", "eps": "N/A"},
            ]
        }
    }
    calls: list[str] = []

    async def fake_get(url, params=None, headers=None):
        calls.append(params["date"])
        if params["date"] == "2026-10-16":
            return _response(json_data=reported)
        return _response(json_data={"data": {"rows": []}})

    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.side_effect = fake_get

    class _FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 19)  # a Monday

    with patch.object(earnings_service, "date", _FakeDate):
        result = await earnings_service.get_earnings_results(client, days=3)

    # Monday, Friday, Thursday: the weekend is skipped.
    assert calls == ["2026-10-19", "2026-10-16", "2026-10-15"]
    assert result["start_date"] == "2026-10-15"
    assert result["end_date"] == "2026-10-19"
    assert [r["symbol"] for r in result["results"]] == ["TRV"]
    row = result["results"][0]
    assert row["eps_actual"] == 9.18
    assert row["outcome"] == "beat"
    assert row["session"] == "pre-market"
    assert result["summary"] == {"reported": 1, "beat": 1, "miss": 0, "inline": 0}


@pytest.mark.asyncio
async def test_get_earnings_results_none_when_every_day_fails():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.return_value = _response(status_code=500)

    assert await earnings_service.get_earnings_results(client, days=2) is None
