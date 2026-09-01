"""Tests for shared portfolio valuation, history building and snapshots."""

from datetime import datetime, timedelta, timezone

import pytest

from app.runtime import portfolio_valuation as pv
from app.runtime.portfolio_snapshot import capture_snapshot

pytestmark = pytest.mark.asyncio


class _StubClassifier:
    def __init__(self, classify_async):
        self.classify_async = classify_async


class _StubIbkrRepo:
    def __init__(self, positions: list[dict] | None = None):
        self._positions = positions or []

    async def list_positions(self) -> list[dict]:
        return self._positions


def test_aggregate_holdings_merges_symbols_with_weighted_cost():
    holdings = pv.aggregate_holdings(
        [
            {"symbol": "aapl", "quantity": 10, "avg_cost": 100.0},
            {"symbol": "AAPL", "quantity": 10, "avg_cost": 200.0},
            {"symbol": "MSFT", "quantity": 1, "avg_cost": 50.0},
        ]
    )

    by_symbol = {h["symbol"]: h for h in holdings}
    assert by_symbol["AAPL"]["quantity"] == 20
    assert by_symbol["AAPL"]["avg_cost"] == pytest.approx(150.0)
    assert by_symbol["AAPL"]["cost_basis"] == pytest.approx(3000.0)
    # Sorted by cost basis, largest first.
    assert holdings[0]["symbol"] == "AAPL"


def test_aggregate_holdings_skips_unusable_rows():
    holdings = pv.aggregate_holdings(
        [
            {"symbol": "", "quantity": 5, "avg_cost": 1.0},
            {"symbol": "ZERO", "quantity": 0, "avg_cost": 1.0},
            {"symbol": "BAD", "quantity": "not-a-number", "avg_cost": 1.0},
            {"symbol": "OK", "quantity": 2, "avg_cost": 3.0},
        ]
    )

    assert [h["symbol"] for h in holdings] == ["OK"]


async def test_resolve_holdings_auto_prefers_ibkr_stock_positions(portfolio_repo):
    await portfolio_repo.create_position(
        {"symbol": "MANUAL", "quantity": 1, "avg_cost": 10.0}
    )
    ibkr = _StubIbkrRepo(
        [
            {"symbol": "IBKR1", "sec_type": "STK", "quantity": 3, "avg_cost": 20.0},
            {"symbol": "OPT1", "sec_type": "OPT", "quantity": 1, "avg_cost": 5.0},
        ]
    )

    source, holdings = await pv.resolve_holdings(portfolio_repo, ibkr, "auto")

    assert source == "ibkr"
    # Non-stock legs are excluded.
    assert [h["symbol"] for h in holdings] == ["IBKR1"]


async def test_resolve_holdings_auto_falls_back_to_manual(portfolio_repo):
    await portfolio_repo.create_position(
        {"symbol": "MANUAL", "quantity": 1, "avg_cost": 10.0}
    )

    source, holdings = await pv.resolve_holdings(
        portfolio_repo, _StubIbkrRepo(), "auto"
    )

    assert source == "manual"
    assert [h["symbol"] for h in holdings] == ["MANUAL"]


async def test_resolve_holdings_honours_explicit_source(portfolio_repo):
    await portfolio_repo.create_position(
        {"symbol": "MANUAL", "quantity": 1, "avg_cost": 10.0}
    )
    ibkr = _StubIbkrRepo(
        [{"symbol": "IBKR1", "sec_type": "STK", "quantity": 3, "avg_cost": 20.0}]
    )

    source, holdings = await pv.resolve_holdings(portfolio_repo, ibkr, "manual")

    assert source == "manual"
    assert [h["symbol"] for h in holdings] == ["MANUAL"]


async def test_value_holdings_totals_and_weights(monkeypatch):
    async def fake_quote(symbol):
        return {"price": 120.0, "change_percent": 2.0} if symbol == "AAPL" else None

    monkeypatch.setattr(pv, "get_stock_info", fake_quote)

    result = await pv.value_holdings(
        [
            {
                "symbol": "AAPL",
                "quantity": 10,
                "avg_cost": 100.0,
                "cost_basis": 1000.0,
                "currency": "USD",
            },
            {
                "symbol": "NOQUOTE",
                "quantity": 5,
                "avg_cost": 20.0,
                "cost_basis": 100.0,
                "currency": "USD",
            },
        ]
    )

    totals = result["totals"]
    # NOQUOTE falls back to cost, so it contributes value but no PnL.
    assert totals["market_value"] == pytest.approx(1300.0)
    assert totals["cost_basis"] == pytest.approx(1100.0)
    assert totals["unrealized_pnl"] == pytest.approx(200.0)

    by_symbol = {p["symbol"]: p for p in result["positions"]}
    assert by_symbol["NOQUOTE"]["market_price"] is None
    assert by_symbol["AAPL"]["weight_percent"] == pytest.approx(1200 / 1300 * 100)


async def test_value_holdings_handles_empty_input():
    result = await pv.value_holdings([])
    assert result["totals"]["positions"] == 0
    assert result["positions"] == []


def test_forward_fill_carries_last_close_across_gaps():
    series = [
        {"t": "2026-01-02", "close": 10.0},
        {"t": "2026-01-05", "close": 12.0},
    ]
    timeline = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-05"]

    filled = pv._forward_filled(series, timeline)

    # Before the first bar we reuse the earliest close rather than dropping the day.
    assert filled["2026-01-01"] == 10.0
    assert filled["2026-01-03"] == 10.0
    assert filled["2026-01-05"] == 12.0


async def test_build_value_history_reconstructs_series(monkeypatch):
    series = {
        "AAPL": [
            {"t": "2026-01-02", "close": 100.0},
            {"t": "2026-01-03", "close": 110.0},
        ],
        "MSFT": [{"t": "2026-01-03", "close": 50.0}],
    }

    async def fake_series(symbol, range_key):
        return series.get(symbol, [])

    monkeypatch.setattr(pv, "get_price_series", fake_series)

    holdings = [
        {"symbol": "AAPL", "quantity": 2, "avg_cost": 90.0, "cost_basis": 180.0},
        {"symbol": "MSFT", "quantity": 1, "avg_cost": 40.0, "cost_basis": 40.0},
    ]

    history = await pv.build_value_history(holdings, "1M")

    assert history["range"] == "1M"
    # MSFT has no bar on the 2nd, so its first close is carried backwards.
    assert history["points"][0]["value"] == pytest.approx(2 * 100 + 50)
    assert history["points"][1]["value"] == pytest.approx(2 * 110 + 50)
    assert history["cost_basis"] == pytest.approx(220.0)
    assert history["points"][0]["source"] == "reconstructed"
    assert history["change"] == pytest.approx(20.0)


async def test_build_value_history_prefers_snapshots_over_reconstruction(monkeypatch):
    async def fake_series(symbol, range_key):
        return [
            {"t": "2026-01-02", "close": 100.0},
            {"t": "2026-01-03", "close": 110.0},
        ]

    monkeypatch.setattr(pv, "get_price_series", fake_series)

    holdings = [{"symbol": "AAPL", "quantity": 1, "avg_cost": 90.0, "cost_basis": 90.0}]
    snapshots = [
        {
            "captured_at": "2026-01-02T21:00:00+00:00",
            "market_value": 555.0,
            "cost_basis": 400.0,
        }
    ]

    history = await pv.build_value_history(holdings, "1M", snapshots=snapshots)

    first, second = history["points"]
    assert first["source"] == "snapshot"
    assert first["value"] == 555.0
    assert first["cost_basis"] == 400.0
    assert second["source"] == "reconstructed"
    assert second["value"] == pytest.approx(110.0)


async def test_build_value_history_appends_live_totals(monkeypatch):
    async def fake_series(symbol, range_key):
        return [{"t": "2020-01-02", "close": 100.0}]

    monkeypatch.setattr(pv, "get_price_series", fake_series)

    history = await pv.build_value_history(
        [{"symbol": "AAPL", "quantity": 1, "avg_cost": 90.0, "cost_basis": 90.0}],
        "1M",
        live_totals={
            "market_value": 200.0,
            "cost_basis": 90.0,
            "unrealized_pnl": 110.0,
            "unrealized_pnl_percent": 122.2,
        },
    )

    assert history["points"][-1]["source"] == "live"
    assert history["end_value"] == 200.0


async def test_build_value_history_reports_symbols_without_history(monkeypatch):
    async def fake_series(symbol, range_key):
        return [{"t": "2026-01-02", "close": 100.0}] if symbol == "AAPL" else []

    monkeypatch.setattr(pv, "get_price_series", fake_series)

    history = await pv.build_value_history(
        [
            {"symbol": "AAPL", "quantity": 1, "avg_cost": 90.0, "cost_basis": 90.0},
            {"symbol": "GHOST", "quantity": 1, "avg_cost": 5.0, "cost_basis": 5.0},
        ],
        "1M",
    )

    assert history["missing_symbols"] == ["GHOST"]
    assert history["points"][0]["value"] == pytest.approx(100.0)


async def test_build_value_history_without_holdings():
    history = await pv.build_value_history([], "1M")
    assert history["points"] == []
    assert history["start_value"] is None


async def test_build_asset_insights_attaches_stats(monkeypatch):
    async def fake_stats(symbol, price):
        if symbol == "BROKEN":
            raise RuntimeError("boom")
        return {"symbol": symbol, "flags": [{"code": "at_ath"}]}

    monkeypatch.setattr(pv, "get_symbol_stats", fake_stats)

    enriched = await pv.build_asset_insights(
        [
            {"symbol": "SMALL", "market_price": 1.0, "market_value": 10.0},
            {"symbol": "BROKEN", "market_price": 2.0, "market_value": 50.0},
            {"symbol": "BIG", "market_price": 3.0, "market_value": 100.0},
        ]
    )

    # Sorted by market value, and a failing symbol degrades to stats=None.
    assert [p["symbol"] for p in enriched] == ["BIG", "BROKEN", "SMALL"]
    assert enriched[1]["stats"] is None
    assert enriched[0]["stats"]["flags"][0]["code"] == "at_ath"


async def test_build_diversification_groups_by_sector_and_flags_concentration(
    monkeypatch,
):
    async def fake_classify(symbols):
        table = {
            "AAPL": {"category": "EQUITY", "sector": "Technology"},
            "MSFT": {"category": "EQUITY", "sector": "Technology"},
            "BTC": {"category": "crypto", "sector": None},
        }
        return [table.get(s) for s in symbols]

    monkeypatch.setattr(
        pv, "get_shared_classifier", lambda: _StubClassifier(fake_classify)
    )

    result = await pv.build_diversification(
        [
            {"symbol": "AAPL", "market_value": 700.0, "weight_percent": 70.0},
            {"symbol": "MSFT", "market_value": 200.0, "weight_percent": 20.0},
            {"symbol": "BTC", "market_value": 100.0, "weight_percent": 10.0},
        ]
    )

    sectors = {s["sector"]: s for s in result["sectors"]}
    assert sectors["Technology"]["weight_percent"] == pytest.approx(90.0)
    assert sectors["Technology"]["symbols"] == ["AAPL", "MSFT"]
    assert sectors["Crypto"]["weight_percent"] == pytest.approx(10.0)

    diversification = result["diversification"]
    # AAPL alone is 70% of the book, so this reads as concentrated.
    assert diversification["label"] == "concentrated"
    assert diversification["tone"] == "bearish"
    assert diversification["top_holding"] == {"symbol": "AAPL", "weight_percent": 70.0}
    assert diversification["top_sector"]["sector"] == "Technology"
    assert diversification["holding_hhi"] == pytest.approx(0.7**2 + 0.2**2 + 0.1**2)


async def test_build_diversification_labels_a_spread_book_diversified(monkeypatch):
    async def fake_classify(symbols):
        sectors = ["Technology", "Healthcare", "Energy", "Financials", "Industrials"]
        return [{"category": "EQUITY", "sector": s} for s in sectors[: len(symbols)]]

    monkeypatch.setattr(
        pv, "get_shared_classifier", lambda: _StubClassifier(fake_classify)
    )

    result = await pv.build_diversification(
        [
            {"symbol": s, "market_value": 20.0, "weight_percent": 20.0}
            for s in ["A", "B", "C", "D", "E"]
        ]
    )

    assert result["diversification"]["label"] == "diversified"
    assert result["diversification"]["tone"] == "bullish"
    assert len(result["sectors"]) == 5


async def test_build_diversification_handles_empty_input():
    result = await pv.build_diversification([])
    assert result["sectors"] == []
    assert result["diversification"]["label"] == "unrated"


async def test_snapshot_repo_round_trip(portfolio_repo):
    now = datetime.now(timezone.utc)
    await portfolio_repo.add_snapshot(
        {
            "source": "manual",
            "captured_at": now - timedelta(days=2),
            "market_value": 100.0,
            "cost_basis": 90.0,
            "unrealized_pnl": 10.0,
            "unrealized_pnl_percent": 11.1,
            "positions": 1,
        }
    )
    latest_payload = await portfolio_repo.add_snapshot(
        {
            "source": "manual",
            "captured_at": now,
            "market_value": 120.0,
            "cost_basis": 90.0,
            "unrealized_pnl": 30.0,
            "unrealized_pnl_percent": 33.3,
            "positions": 1,
        }
    )

    all_snapshots = await portfolio_repo.list_snapshots(source="manual")
    assert [s["market_value"] for s in all_snapshots] == [100.0, 120.0]

    recent = await portfolio_repo.list_snapshots(since=now - timedelta(hours=1))
    assert [s["market_value"] for s in recent] == [120.0]

    latest = await portfolio_repo.latest_snapshot()
    assert latest["id"] == latest_payload["id"]

    assert await portfolio_repo.list_snapshots(source="ibkr") == []


async def test_capture_snapshot_persists_current_valuation(portfolio_repo, monkeypatch):
    await portfolio_repo.create_position(
        {"symbol": "AAPL", "quantity": 2, "avg_cost": 100.0}
    )

    async def fake_quote(symbol):
        return {"price": 150.0}

    monkeypatch.setattr(pv, "get_stock_info", fake_quote)

    snapshot = await capture_snapshot(portfolio_repo, _StubIbkrRepo())

    assert snapshot["source"] == "manual"
    assert snapshot["market_value"] == pytest.approx(300.0)
    assert snapshot["unrealized_pnl"] == pytest.approx(100.0)
    assert snapshot["breakdown"][0]["symbol"] == "AAPL"


async def test_capture_snapshot_skips_empty_portfolio(portfolio_repo):
    assert await capture_snapshot(portfolio_repo, _StubIbkrRepo()) is None
    assert await portfolio_repo.latest_snapshot() is None


async def test_build_value_history_keeps_reconstruction_on_intraday_timelines(
    monkeypatch,
):
    """Day-indexed snapshots must not flatten every bar of an intraday day."""

    async def fake_series(symbol, range_key):
        return [
            {"t": "2026-01-02T14:00:00+00:00", "close": 100.0},
            {"t": "2026-01-02T15:00:00+00:00", "close": 110.0},
        ]

    monkeypatch.setattr(pv, "get_price_series", fake_series)

    history = await pv.build_value_history(
        [{"symbol": "AAPL", "quantity": 1, "avg_cost": 90.0, "cost_basis": 90.0}],
        "1W",
        snapshots=[
            {
                "captured_at": "2026-01-02T21:00:00+00:00",
                "market_value": 555.0,
                "cost_basis": 400.0,
            }
        ],
    )

    assert [p["source"] for p in history["points"]] == [
        "reconstructed",
        "reconstructed",
    ]
    assert [p["value"] for p in history["points"]] == [100.0, 110.0]
