"""Tests for valuing IBKR positions with IBKR's own marks and listings."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.runtime import portfolio_valuation as pv
from app.services.ibkr import ibkr_contract_label, position_row, quote_symbol


def _contract(**overrides):
    base = {
        "symbol": "ARKG",
        "secType": "STK",
        "exchange": "LSE",
        "primaryExchange": "",
        "currency": "USD",
        "conId": 1,
        "localSymbol": "",
        "lastTradeDateOrContractMonth": "",
        "strike": 0.0,
        "right": "",
        "multiplier": "",
    }
    return SimpleNamespace(**{**base, **overrides})


def _iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) - delta).isoformat()


def test_position_row_takes_ibkr_mark_and_option_terms():
    position = SimpleNamespace(
        account="U1",
        contract=_contract(symbol="DRAM", secType="OPT", exchange=""),
        position=1.0,
        avgCost=1215.8,
    )
    mark = SimpleNamespace(
        contract=_contract(
            symbol="DRAM",
            secType="OPT",
            exchange="",
            localSymbol="DRAM  261218C00100000",
            lastTradeDateOrContractMonth="20261218",
            strike=100.0,
            right="C",
            multiplier="100",
        ),
        marketPrice=14.5,
        marketValue=1450.0,
        unrealizedPNL=234.2,
    )

    row = position_row(position, mark)

    assert row["market_price"] == 14.5
    assert row["market_value"] == 1450.0
    assert row["multiplier"] == 100.0
    assert ibkr_contract_label(row) == "DRAM 2026-12-18 100 C"


def test_position_row_without_mark_drops_ib_sentinels():
    position = SimpleNamespace(
        account="U1", contract=_contract(), position=75.0, avgCost=7.66
    )

    row = position_row(position)

    assert row["market_price"] is None
    assert row["exchange"] == "LSE"


@pytest.mark.parametrize(
    "row, expected",
    [
        ({"symbol": "ARKG", "sec_type": "STK", "exchange": "LSE"}, "ARKG.L"),
        (
            {"symbol": "ASML", "sec_type": "STK", "exchange": "NASDAQ"},
            "ASML",
        ),
        ({"symbol": "BRK B", "sec_type": "STK", "exchange": "NYSE"}, "BRK-B"),
        ({"symbol": "DRAM", "sec_type": "OPT", "exchange": ""}, None),
    ],
)
def test_quote_symbol_maps_listing(row, expected):
    assert quote_symbol(row) == expected


def test_choose_price_order():
    fresh = {"ibkr_market_price": 9.0, "synced_at": _iso(timedelta(minutes=1))}
    stale = {"ibkr_market_price": 9.0, "synced_at": _iso(timedelta(days=8))}

    assert pv.choose_price(fresh, 8.8) == (9.0, "ibkr")
    assert pv.choose_price(stale, 8.8) == (8.8, "yahoo")
    assert pv.choose_price(stale, None) == (9.0, "ibkr_stale")
    assert pv.choose_price({}, None) == (None, "none")


@pytest.mark.asyncio
async def test_value_holdings_quotes_foreign_listing(monkeypatch):
    seen = []

    async def fake_quote(symbol):
        seen.append(symbol)
        return {"price": 8.8}

    monkeypatch.setattr(pv, "get_stock_info", fake_quote)
    holdings = pv.aggregate_holdings(
        [
            {
                "symbol": "ARKG",
                "quote_symbol": "ARKG.L",
                "quantity": 75,
                "avg_cost": 7.66,
            }
        ]
    )

    result = await pv.value_holdings(holdings)

    assert seen == ["ARKG.L"]
    position = result["positions"][0]
    assert position["symbol"] == "ARKG"
    assert position["market_value"] == pytest.approx(660.0)
    assert position["price_source"] == "yahoo"
