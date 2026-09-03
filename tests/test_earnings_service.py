from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.services import earnings_service


@pytest.fixture(autouse=True)
def _clear_cache():
    earnings_service._reset_cache_for_tests()
    yield
    earnings_service._reset_cache_for_tests()


def _response(status_code=200, json_data=None):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data
    return response


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
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.side_effect = [
        _response(status_code=500, json_data={}),
        _response(json_data={"data": {"rows": []}}),
    ]

    result = await earnings_service.get_earnings_calendar(client, days=2)

    assert result is not None
    assert len(result["days"]) == 2


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
