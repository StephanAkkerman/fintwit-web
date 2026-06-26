import pytest

import app.services.macro_market as macro_market


@pytest.mark.asyncio
async def test_get_macro_snapshot_builds_curves_and_fx_indices(monkeypatch):
    async def fake_quote(symbol: str, asset_hint: str | None = None, prefer_realtime: bool = True):
        quotes = {
            "CRYPTOCAP:TOTAL": {
                "price": 2450000000000,
                "change_percent": 1.25,
                "website": "total",
            },
            "CRYPTOCAP:TOTAL2": {
                "price": 920000000000,
                "change_percent": 0.95,
                "website": "total2",
            },
            "CRYPTOCAP:TOTAL3": {
                "price": 480000000000,
                "change_percent": 0.74,
                "website": "total3",
            },
            "CRYPTOCAP:BTC.D": {
                "price": 53.1,
                "change_percent": -0.11,
                "website": "btcd",
            },
            "CRYPTOCAP:ETH.D": {
                "price": 16.4,
                "change_percent": 0.09,
                "website": "ethd",
            },
            "CRYPTOCAP:OTHERS.D": {
                "price": 30.5,
                "change_percent": 0.05,
                "website": "othersd",
            },
            "CRYPTOCAP:TOTALDEFI.D": {
                "price": 2.9,
                "change_percent": 0.03,
                "website": "defi",
            },
            "CRYPTOCAP:USDT.D": {
                "price": 6.2,
                "change_percent": -0.02,
                "website": "usdt",
            },
            "CRYPTOCAP:USDC.D": {
                "price": 1.7,
                "change_percent": 0.01,
                "website": "usdc",
            },
            "TVC:US01Y": {"price": 4.11, "change_percent": 0.03, "website": "u1"},
            "TVC:US02Y": {"price": 4.31, "change_percent": 0.04, "website": "u2"},
            "TVC:US10Y": {"price": 4.73, "change_percent": 0.05, "website": "u10"},
            "TVC:EU02Y": {"price": 2.11, "change_percent": -0.01, "website": "e2"},
            "TVC:EU10Y": {"price": 2.62, "change_percent": 0.02, "website": "e10"},
            "AMEX:SPY": {"price": 585.12, "change_percent": 0.38, "website": "spy"},
            "NASDAQ:NDX": {"price": 20234.55, "change_percent": 0.52, "website": "ndx"},
            "USI:PCC": {"price": 101.22, "change_percent": 0.12, "website": "pcc"},
            "USI:PCCE": {"price": 99.81, "change_percent": -0.04, "website": "pcce"},
            "TVC:VIX": {"price": 14.8, "change_percent": -0.21, "website": "vix"},
            "TVC:SPX": {"price": 5240.18, "change_percent": 0.44, "website": "spx"},
            "DXY": {"price": 104.23, "change_percent": 0.18, "website": "dxy"},
            "EXY": {"price": 109.12, "change_percent": -0.08, "website": "exy"},
            "BXY": {"price": 126.77, "change_percent": 0.07, "website": "bxy"},
            "JXY": {"price": 66.33, "change_percent": -0.03, "website": "jxy"},
        }
        return quotes.get(symbol)

    async def fake_market_hours():
        return [
            {"exchange": "NYSE", "is_open": True, "session": "Open"},
            {"exchange": "NASDAQ", "is_open": True, "session": "Open"},
        ]

    monkeypatch.setattr(macro_market, "get_tradingview_quote", fake_quote)
    monkeypatch.setattr(macro_market, "get_stock_market_hours", fake_market_hours)
    macro_market._reset_cache_for_tests()

    snapshot = await macro_market.get_macro_snapshot()

    assert snapshot is not None
    assert snapshot["yield_curves"]
    assert snapshot["crypto_indices"]
    assert snapshot["stock_forex_indices"]
    assert snapshot["fx_indices"]
    assert snapshot["stock_forex_visible"] is True

    us_curve = next(
        curve for curve in snapshot["yield_curves"] if curve["label"] == "US"
    )
    assert us_curve["spread_2s10s"] == pytest.approx(0.42)
    assert any(point["maturity"] == "10Y" for point in us_curve["points"])

    total = next(
        index for index in snapshot["crypto_indices"] if index["symbol"] == "TOTAL"
    )
    assert total["price"] == pytest.approx(2_450_000_000_000)

    spy = next(
        index for index in snapshot["stock_forex_indices"] if index["symbol"] == "SPY"
    )
    assert spy["price"] == pytest.approx(585.12)

    dxy = next(index for index in snapshot["fx_indices"] if index["symbol"] == "DXY")
    assert dxy["price"] == pytest.approx(104.23)
