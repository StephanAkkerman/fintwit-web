from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.services.option_contract_service import (
    get_option_contract,
    match_expiration,
    parse_expiry,
)

POSTED = date(2026, 10, 15)


@pytest.mark.parametrize(
    "expiry,expected",
    [
        ("11/06/2026", date(2026, 11, 6)),
        ("11/06/26", date(2026, 11, 6)),
        ("11/20", date(2026, 11, 20)),
        ("1/16", date(2027, 1, 16)),
        ("2026-12-18", date(2026, 12, 18)),
        ("NOV", date(2026, 11, 20)),
        ("Nov 21", date(2026, 11, 21)),
        ("JAN", date(2027, 1, 15)),
        ("11/20exp", date(2026, 11, 20)),
        ("soon", None),
        ("", None),
    ],
)
def test_parse_expiry(expiry, expected):
    assert parse_expiry(expiry, POSTED) == expected


def test_match_expiration_allows_a_holiday_shift_only():
    listed = ["2026-11-19", "2026-11-27"]

    assert match_expiration(date(2026, 11, 20), listed) == "2026-11-19"
    assert match_expiration(date(2026, 11, 13), listed) is None


def _chain(expiration):
    return {
        "symbol": "AAPL",
        "underlying": {"last_price": 352.1},
        "expirations": ["2026-10-16", "2026-11-06"],
        "expiration": expiration,
        "contracts": [
            {
                "option_type": "CALL",
                "strike": 350.0,
                "bid": 4.0,
                "ask": 4.4,
                "last_price": 4.25,
                "volume": 120,
                "open_interest": 900,
                "implied_volatility": 0.31,
                "change_percent": 12.5,
                "in_the_money": True,
            },
            {"option_type": "PUT", "strike": 350.0, "bid": 2.0, "ask": 2.2},
        ],
        "source": "yfinance",
    }


@pytest.mark.asyncio
async def test_get_option_contract_quotes_the_named_contract():
    fetch = AsyncMock(
        side_effect=lambda symbol, expiration=None: _chain(expiration or "2026-10-16")
    )
    with patch("app.services.option_contract_service.get_options_chain", fetch):
        quote = await get_option_contract(
            "aapl", "call", 350, "11/06", as_of=POSTED, today=POSTED
        )

    assert quote["status"] == "listed"
    assert quote["expiration"] == "2026-11-06"
    assert quote["last_price"] == 4.25
    assert quote["mid"] == 4.2
    assert quote["underlying_price"] == 352.1
    fetch.assert_awaited_with("AAPL", "2026-11-06")


@pytest.mark.asyncio
async def test_get_option_contract_reports_an_expired_contract_without_fetching():
    fetch = AsyncMock()
    with patch("app.services.option_contract_service.get_options_chain", fetch):
        quote = await get_option_contract(
            "AAPL", "PUT", 350, "10/02/2026", today=POSTED
        )

    assert quote["status"] == "expired"
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_option_contract_is_none_for_an_unlisted_strike():
    fetch = AsyncMock(
        side_effect=lambda symbol, expiration=None: _chain(expiration or "2026-10-16")
    )
    with patch("app.services.option_contract_service.get_options_chain", fetch):
        quote = await get_option_contract(
            "AAPL", "CALL", 999, "11/06/2026", today=POSTED
        )

    assert quote is None
