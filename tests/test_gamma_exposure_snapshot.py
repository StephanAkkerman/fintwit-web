from unittest.mock import AsyncMock, patch

import pytest

from app.runtime.gamma_exposure_snapshot import capture_snapshot

_ESTIMATE = {
    "symbol": "SPY",
    "spot_price": 500.0,
    "net_gex": -1.5e9,
    "call_gex": 2.0e9,
    "put_gex": -3.5e9,
    "flip_point": 505.0,
    "regime": "negative",
    "expirations_used": ["2026-10-17"],
    "by_strike": [],
    "as_of": "2026-09-27T00:00:00+00:00",
    "source": "yfinance-bs-estimate",
}


@pytest.mark.asyncio
async def test_capture_snapshot_persists_estimate(gamma_exposure_repo):
    with patch(
        "app.runtime.gamma_exposure_snapshot.get_gamma_exposure",
        AsyncMock(return_value=_ESTIMATE),
    ):
        stored = await capture_snapshot(gamma_exposure_repo, "SPY")

    assert stored is not None
    assert stored["symbol"] == "SPY"
    assert stored["net_gex"] == -1.5e9
    assert stored["regime"] == "negative"

    latest = await gamma_exposure_repo.latest_snapshot(symbol="SPY")
    assert latest is not None
    assert latest["flip_point"] == 505.0


@pytest.mark.asyncio
async def test_capture_snapshot_returns_none_when_chain_unavailable(
    gamma_exposure_repo,
):
    with patch(
        "app.runtime.gamma_exposure_snapshot.get_gamma_exposure",
        AsyncMock(return_value=None),
    ):
        stored = await capture_snapshot(gamma_exposure_repo, "SPY")

    assert stored is None
    assert await gamma_exposure_repo.latest_snapshot(symbol="SPY") is None
