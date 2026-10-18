from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services import put_call_service as svc


@pytest.fixture(autouse=True)
def _reset_cache():
    svc._reset_cache_for_tests()
    yield
    svc._reset_cache_for_tests()


def _payload(total="0.92", equity="0.65", index="1.05"):
    return {
        "ratios": [
            {"name": "TOTAL PUT/CALL RATIO", "value": total},
            {"name": "INDEX PUT/CALL RATIO", "value": index},
            {"name": "EQUITY PUT/CALL RATIO", "value": equity},
            {"name": "KPI BINARY OPTIONS PUT/CALL RATIO", "value": "0.00"},
        ],
        "SUM OF ALL PRODUCTS": [
            {"name": "VOLUME", "call": 10401864, "put": 9619756, "total": 20021620},
            {"name": "OPEN INTEREST", "call": 1, "put": 2, "total": 3},
        ],
        "EQUITY OPTIONS": [{"name": "VOLUME", "call": 3284761, "put": 2130650}],
    }


def _response(status_code=200, json_data=None):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data
    return response


def test_parse_daily_maps_ratios_and_volume():
    parsed = svc.parse_daily(_payload(), "2026-10-16")

    assert parsed == {
        "date": "2026-10-16",
        "ratios": {"total": 0.92, "index": 1.05, "equity": 0.65},
        "volume": {
            "total": {"call": 10401864, "put": 9619756},
            "equity": {"call": 3284761, "put": 2130650},
        },
    }


def test_parse_daily_without_total_ratio_is_none():
    assert svc.parse_daily({"ratios": []}, "2026-10-16") is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.85, "fear"), (0.80, "fear"), (0.65, "neutral"), (0.50, "greed"), (None, None)],
)
def test_classify_equity_ratio(value, expected):
    assert svc.classify_equity_ratio(value) == expected


def test_build_summary_latest_change_average_and_history():
    sessions = [
        svc.parse_daily(_payload("0.90", "0.85"), "2026-10-16"),
        svc.parse_daily(_payload("0.80", "0.55"), "2026-10-15"),
        svc.parse_daily(_payload("0.70", "0.45"), "2026-10-14"),
    ]

    summary = svc.build_summary(sessions)

    assert summary["date"] == "2026-10-16"
    total = summary["ratios"][0]
    assert total == {
        "key": "total",
        "value": 0.9,
        "previous": 0.8,
        "change": 0.1,
        "average": 0.8,
    }
    assert summary["sentiment"] == "fear"
    # History runs oldest first for the sparkline.
    assert [h["date"] for h in summary["history"]] == [
        "2026-10-14",
        "2026-10-15",
        "2026-10-16",
    ]
    assert summary["history"][0]["equity"] == 0.45


def test_build_summary_empty_is_none():
    assert svc.build_summary([]) is None


@pytest.mark.asyncio
async def test_get_put_call_ratios_skips_days_without_a_file():
    # 2026-10-19 is a Monday: today has no file yet (403), Friday does.
    def fake_get(url, **_):
        if "2026-10-16" in url:
            return _response(json_data=_payload())
        if "2026-10-15" in url:
            return _response(json_data=_payload("0.80", "0.62"))
        return _response(status_code=403)

    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.side_effect = fake_get

    with patch.object(svc, "date") as fake_date:
        fake_date.today.return_value = date(2026, 10, 19)
        result = await svc.get_put_call_ratios(client)

    assert result["date"] == "2026-10-16"
    assert result["ratios"][0]["previous"] == 0.8
    assert len(result["history"]) == 2
    # Weekends are never requested.
    requested = [call.args[0] for call in client.get.call_args_list]
    assert not any("2026-10-18" in url or "2026-10-17" in url for url in requested)

    # Cached: a second call does not hit Cboe again.
    calls = client.get.call_count
    await svc.get_put_call_ratios(client)
    assert client.get.call_count == calls


@pytest.mark.asyncio
async def test_get_put_call_ratios_none_when_cboe_unreachable():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.side_effect = httpx.ConnectError("down")

    assert await svc.get_put_call_ratios(client) is None
