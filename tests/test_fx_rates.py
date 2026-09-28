import pytest

import app.services.fx_rates as fx_rates


@pytest.mark.asyncio
async def test_get_fx_rates_builds_rate_map(monkeypatch):
    async def fake_quote(symbol: str, asset_hint: str | None = None):
        quotes = {
            "FX_IDC:USDEUR": {"price": 0.92},
            "FX_IDC:USDGBP": {"price": 0.79},
            "FX_IDC:USDJPY": {"price": 149.5},
            "FX_IDC:USDCHF": {"price": 0.88},
            "FX_IDC:USDAUD": {"price": 1.52},
            "FX_IDC:USDCAD": {"price": 1.36},
        }
        return quotes.get(symbol)

    monkeypatch.setattr(fx_rates, "get_tradingview_quote", fake_quote)
    fx_rates._reset_cache_for_tests()

    result = await fx_rates.get_fx_rates()

    assert result is not None
    assert result["base"] == "USD"
    assert result["rates"]["EUR"] == pytest.approx(0.92)
    assert result["rates"]["JPY"] == pytest.approx(149.5)
    assert set(result["rates"]) == {"EUR", "GBP", "JPY", "CHF", "AUD", "CAD"}


@pytest.mark.asyncio
async def test_get_fx_rates_drops_failed_quotes(monkeypatch):
    async def fake_quote(symbol: str, asset_hint: str | None = None):
        if symbol == "FX_IDC:USDEUR":
            return {"price": 0.92}
        return None

    monkeypatch.setattr(fx_rates, "get_tradingview_quote", fake_quote)
    fx_rates._reset_cache_for_tests()

    result = await fx_rates.get_fx_rates()

    assert result == {"base": "USD", "rates": {"EUR": 0.92}}


@pytest.mark.asyncio
async def test_get_fx_rates_returns_none_when_all_quotes_fail(monkeypatch):
    async def fake_quote(symbol: str, asset_hint: str | None = None):
        return None

    monkeypatch.setattr(fx_rates, "get_tradingview_quote", fake_quote)
    fx_rates._reset_cache_for_tests()

    result = await fx_rates.get_fx_rates()

    assert result is None


@pytest.mark.asyncio
async def test_get_fx_rates_uses_cache(monkeypatch):
    call_count = 0

    async def fake_quote(symbol: str, asset_hint: str | None = None):
        nonlocal call_count
        call_count += 1
        return {"price": 0.92}

    monkeypatch.setattr(fx_rates, "get_tradingview_quote", fake_quote)
    fx_rates._reset_cache_for_tests()

    first = await fx_rates.get_fx_rates()
    second = await fx_rates.get_fx_rates()

    assert first == second
    assert call_count == len(fx_rates.SUPPORTED_CURRENCIES)
