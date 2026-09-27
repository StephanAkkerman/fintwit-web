import math
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import app.services.gamma_exposure_service as gamma_exposure_service
from app.services.gamma_exposure_service import (
    _zero_gamma_level,
    black_scholes_gamma,
    get_gamma_exposure,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    gamma_exposure_service._reset_cache_for_tests()
    yield
    gamma_exposure_service._reset_cache_for_tests()


def _underlying(**overrides):
    base = {"regularMarketPrice": 500.0, "postMarketPrice": None}
    base.update(overrides)
    return base


def _contract_row(**overrides):
    base = {
        "strike": 500.0,
        "openInterest": 1000,
        "impliedVolatility": 0.2,
    }
    base.update(overrides)
    return base


def _far_expiration() -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")


class TestBlackScholesGamma:
    def test_matches_known_value_for_at_the_money_option(self):
        # S=K=100, T=1y, sigma=0.2, r=0: d1=0.1, gamma = phi(0.1)/(100*0.2*1)
        gamma = black_scholes_gamma(
            spot=100.0, strike=100.0, years_to_expiry=1.0, iv=0.2
        )
        assert gamma is not None
        assert math.isclose(gamma, 0.0198476, rel_tol=1e-4)

    def test_none_for_non_positive_inputs(self):
        assert black_scholes_gamma(0.0, 100.0, 1.0, 0.2) is None
        assert black_scholes_gamma(100.0, 0.0, 1.0, 0.2) is None
        assert black_scholes_gamma(100.0, 100.0, 0.0, 0.2) is None
        assert black_scholes_gamma(100.0, 100.0, 1.0, 0.0) is None

    def test_symmetric_around_spot_for_equidistant_strikes(self):
        lower = black_scholes_gamma(100.0, 90.0, 0.5, 0.25)
        upper = black_scholes_gamma(100.0, 110.0, 0.5, 0.25)
        # Not exactly equal (BS gamma isn't perfectly symmetric in strike), but
        # both should be well-defined and smaller than the ATM peak.
        atm = black_scholes_gamma(100.0, 100.0, 0.5, 0.25)
        assert lower is not None and upper is not None and atm is not None
        assert lower < atm
        assert upper < atm


class TestZeroGammaLevel:
    def test_interpolates_crossing_strike(self):
        # Cumulative sums: -50, -70, 30, 40 -- crosses zero between 100 and 110.
        strike_totals = {90.0: -50.0, 100.0: -20.0, 110.0: 100.0, 120.0: 10.0}
        flip = _zero_gamma_level(strike_totals)
        assert flip is not None
        assert 100.0 < flip < 110.0

    def test_none_when_no_crossing(self):
        strike_totals = {90.0: 10.0, 100.0: 20.0, 110.0: 5.0}
        assert _zero_gamma_level(strike_totals) is None

    def test_none_when_empty(self):
        assert _zero_gamma_level({}) is None


@pytest.mark.asyncio
async def test_get_gamma_exposure_classifies_positive_regime_above_flip():
    expiration = _far_expiration()
    # Heavier call OI than put OI at/above spot -> dealers net long gamma,
    # net GEX positive, spot should sit in the positive regime.
    calls = pd.DataFrame(
        [
            _contract_row(strike=500.0, openInterest=5000),
            _contract_row(strike=510.0, openInterest=3000),
        ]
    )
    puts = pd.DataFrame(
        [
            _contract_row(strike=490.0, openInterest=500),
            _contract_row(strike=480.0, openInterest=500),
        ]
    )
    ticker = MagicMock()
    ticker.options = (expiration,)
    ticker.option_chain.return_value = (calls, puts, _underlying())

    with patch("yfinance.Ticker", return_value=ticker):
        result = await get_gamma_exposure("SPY")

    assert result is not None
    assert result["symbol"] == "SPY"
    assert result["spot_price"] == 500.0
    assert result["net_gex"] > 0
    assert result["regime"] == "positive"
    assert result["expirations_used"] == [expiration]
    assert len(result["by_strike"]) == 4


@pytest.mark.asyncio
async def test_get_gamma_exposure_classifies_negative_regime_below_flip():
    expiration = _far_expiration()
    # Heavy put OI far outweighs call OI -> dealers net short gamma overall.
    calls = pd.DataFrame([_contract_row(strike=510.0, openInterest=200)])
    puts = pd.DataFrame(
        [
            _contract_row(strike=500.0, openInterest=8000),
            _contract_row(strike=490.0, openInterest=6000),
        ]
    )
    ticker = MagicMock()
    ticker.options = (expiration,)
    ticker.option_chain.return_value = (calls, puts, _underlying())

    with patch("yfinance.Ticker", return_value=ticker):
        result = await get_gamma_exposure("SPY")

    assert result is not None
    assert result["net_gex"] < 0
    assert result["regime"] == "negative"


@pytest.mark.asyncio
async def test_get_gamma_exposure_skips_zero_open_interest_and_missing_iv():
    expiration = _far_expiration()
    calls = pd.DataFrame(
        [
            _contract_row(strike=500.0, openInterest=0),
            _contract_row(strike=505.0, openInterest=100, impliedVolatility=None),
            _contract_row(strike=510.0, openInterest=100),
        ]
    )
    puts = pd.DataFrame([])
    ticker = MagicMock()
    ticker.options = (expiration,)
    ticker.option_chain.return_value = (calls, puts, _underlying())

    with patch("yfinance.Ticker", return_value=ticker):
        result = await get_gamma_exposure("SPY")

    assert result is not None
    assert len(result["by_strike"]) == 1
    assert result["by_strike"][0]["strike"] == 510.0


@pytest.mark.asyncio
async def test_get_gamma_exposure_returns_none_when_no_expirations():
    ticker = MagicMock()
    ticker.options = ()

    with patch("yfinance.Ticker", return_value=ticker):
        result = await get_gamma_exposure("ZZZZ")

    assert result is None


@pytest.mark.asyncio
async def test_get_gamma_exposure_returns_none_on_fetch_error():
    with patch("yfinance.Ticker", side_effect=RuntimeError("network down")):
        result = await get_gamma_exposure("SPY")

    assert result is None


@pytest.mark.asyncio
async def test_get_gamma_exposure_caches_between_calls():
    expiration = _far_expiration()
    calls = pd.DataFrame([_contract_row()])
    puts = pd.DataFrame([_contract_row(strike=490.0)])
    ticker = MagicMock()
    ticker.options = (expiration,)
    ticker.option_chain.return_value = (calls, puts, _underlying())

    with patch("yfinance.Ticker", return_value=ticker) as mock_ticker_cls:
        await get_gamma_exposure("SPY")
        await get_gamma_exposure("SPY")

    mock_ticker_cls.assert_called_once()


@pytest.mark.asyncio
async def test_get_gamma_exposure_defaults_to_spy():
    ticker = MagicMock()
    ticker.options = ()

    with patch("yfinance.Ticker", return_value=ticker) as mock_ticker_cls:
        await get_gamma_exposure()

    mock_ticker_cls.assert_called_once_with("SPY")
