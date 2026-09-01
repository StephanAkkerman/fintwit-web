"""Tests for extended_hours_service window logic and snapshot shape."""

import pytest

pytestmark = pytest.mark.asyncio


def test_window_bounds_pre_market():
    from app.services.extended_hours_service import _window_bounds

    start_iso, end_iso, since_utc, until_utc = _window_bounds("pre-market")

    assert "04:00" in start_iso
    assert "09:30" in end_iso
    assert since_utc.tzinfo is None  # must be naive UTC
    assert since_utc < until_utc


def test_window_bounds_after_hours():
    from app.services.extended_hours_service import _window_bounds

    start_iso, end_iso, since_utc, until_utc = _window_bounds("after-hours")

    assert "16:00" in start_iso
    assert "20:00" in end_iso
    assert since_utc.tzinfo is None
    assert since_utc < until_utc


def test_window_bounds_all_sessions_return_naive_utc():
    from app.services.extended_hours_service import _window_bounds

    for session in ("pre-market", "after-hours", "regular", "closed"):
        _, _, since_utc, until_utc = _window_bounds(session)
        assert since_utc.tzinfo is None, f"{session}: since_utc must be naive"
        assert until_utc.tzinfo is None, f"{session}: until_utc must be naive"
        assert since_utc < until_utc, f"{session}: since_utc must precede until_utc"


async def test_get_snapshot_shape(monkeypatch):
    import app.services.extended_hours_service as svc
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.infra.db import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    # Reset module cache so we don't get a stale payload from another test.
    monkeypatch.setattr(svc, "_snapshot_cache", None)

    async def _fake_futures():
        return [
            {
                "label": "ES",
                "symbol": "CME_MINI:ES1!",
                "price": 5800.0,
                "change_pct": 0.3,
            }
        ]

    async def _fake_etfs():
        return [
            {
                "symbol": "SPY",
                "price": 580.0,
                "extended_price": 581.5,
                "extended_change_pct": 0.26,
            }
        ]

    monkeypatch.setattr(svc, "_fetch_futures", _fake_futures)
    monkeypatch.setattr(svc, "_fetch_etfs", _fake_etfs)

    result = await svc.get_snapshot(Session)

    assert result is not None
    assert result["session"] in ("pre-market", "after-hours", "regular", "closed")
    assert isinstance(result["window_start"], str)
    assert isinstance(result["window_end"], str)
    assert isinstance(result["futures"], list)
    assert isinstance(result["etfs"], list)
    assert "total_mentions" in result["tweet_stats"]
    assert "top_tickers" in result["tweet_stats"]
    assert "sentiment_distribution" in result["tweet_stats"]

    await engine.dispose()
