from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api import advisor as advisor_api
from app.api import main as api_main
from app.infra.db import AdvisorCallRow
from app.infra.repos import AdvisorRepo
from app.runtime.advisor_evaluator import evaluate_due_advisor_calls
from app.services.advisor import build_scorecard, normalize_watchlist

HEADERS = {"X-API-Key": "test-api-key"}


class FakeEnricher:
    def __init__(self, prices: dict[str, float], kind: str = "EQUITY"):
        self.prices = prices
        self.kind = kind
        self.calls: list[list[str]] = []

    async def classify(self, symbols):
        self.calls.append(list(symbols))
        return [
            {"symbol": s, "kind": self.kind, "financials": {"price": self.prices[s]}}
            for s in symbols
            if s in self.prices
        ]


@pytest.fixture
async def advisor_repo(db_engine):
    return AdvisorRepo(async_sessionmaker(db_engine, expire_on_commit=False))


async def _backdate(repo: AdvisorRepo, call_id: int, days: int) -> None:
    then = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    async with repo.Session() as s:
        async with s.begin():
            await s.execute(
                update(AdvisorCallRow)
                .where(AdvisorCallRow.id == call_id)
                .values(called_at=then)
            )


def _call(symbol="NVDA", action="buy", price=100.0, kind="EQUITY"):
    return {
        "symbol": symbol,
        "action": action,
        "conviction": "high",
        "price_at_call": price,
        "asset_kind": kind,
        "reasoning": "test",
        "rule": None,
    }


def test_normalize_watchlist():
    assert normalize_watchlist(["$nvda", "NVDA", " aapl ", "not a ticker!", ""]) == [
        "NVDA",
        "AAPL",
    ]


async def test_strategy_round_trip(advisor_repo):
    assert await advisor_repo.get_strategy() == {
        "rules": "",
        "watchlist": [],
        "available_cash": None,
        "cash_currency": None,
        "updated_at": None,
    }
    saved = await advisor_repo.set_strategy(
        "Max 20% per position", ["NVDA"], 5000.0, "EUR"
    )
    assert saved["rules"] == "Max 20% per position"
    assert saved["watchlist"] == ["NVDA"]
    assert saved["available_cash"] == 5000.0
    assert saved["cash_currency"] == "EUR"
    assert saved["updated_at"]

    again = await advisor_repo.set_strategy("Max 10%", [])
    assert again["rules"] == "Max 10%"
    assert again["watchlist"] == []
    assert again["available_cash"] is None
    assert again["cash_currency"] is None


async def test_grading_due_calls(advisor_repo):
    buy = await advisor_repo.create_call(_call("NVDA", "buy", 100.0))
    sell = await advisor_repo.create_call(_call("TSLA", "sell", 200.0))
    watch = await advisor_repo.create_call(_call("AMD", "watch", 50.0))
    fresh = await advisor_repo.create_call(_call("AAPL", "buy", 10.0))
    for call in (buy, sell, watch):
        await _backdate(advisor_repo, call["id"], 8)

    enricher = FakeEnricher({"NVDA": 110.0, "TSLA": 180.0, "AMD": 60.0, "AAPL": 11})
    written = await evaluate_due_advisor_calls(advisor_repo, enricher)

    # Only the 7d horizon is due, and watch notes are never graded.
    assert written == 2
    calls = {c["symbol"]: c for c in await advisor_repo.list_calls()}
    assert calls["NVDA"]["results"]["7"]["return_pct"] == pytest.approx(10.0)
    assert calls["NVDA"]["results"]["7"]["correct"] is True
    assert calls["TSLA"]["results"]["7"]["correct"] is True  # sold before a drop
    assert calls["AMD"]["results"] == {}
    assert calls[fresh["symbol"]]["results"] == {}

    # Already graded calls are not graded again.
    assert await evaluate_due_advisor_calls(advisor_repo, enricher) == 0

    card = build_scorecard(
        await advisor_repo.graded_calls(), await advisor_repo.count_calls()
    )
    assert card["total_calls"] == 4
    seven = card["horizons"]["7"]
    assert seven["graded"] == 2
    assert seven["hit_rate"] == 1.0
    # +10% on the buy, +10% from selling before a 10% drop.
    assert seven["avg_return_pct"] == pytest.approx(10.0)
    assert set(seven["by_action"]) == {"buy", "sell"}
    assert card["horizons"]["30"]["graded"] == 0


async def test_kind_change_is_excluded(advisor_repo):
    call = await advisor_repo.create_call(_call("BTC", "buy", 100.0, kind="CRYPTO"))
    await _backdate(advisor_repo, call["id"], 31)

    await evaluate_due_advisor_calls(advisor_repo, FakeEnricher({"BTC": 50.0}))

    [graded] = await advisor_repo.list_calls()
    assert graded["results"]["7"]["excluded"] is True
    card = build_scorecard(await advisor_repo.graded_calls(), 1)
    assert card["horizons"]["7"]["graded"] == 0


async def test_list_calls_filters(advisor_repo):
    old = await advisor_repo.create_call(_call("NVDA"))
    await advisor_repo.create_call(_call("AAPL"))
    await _backdate(advisor_repo, old["id"], 3)

    assert [c["symbol"] for c in await advisor_repo.list_calls(symbol="nvda")] == [
        "NVDA"
    ]
    assert [c["symbol"] for c in await advisor_repo.list_calls(since_hours=24)] == [
        "AAPL"
    ]


@pytest.fixture
async def api(async_client, advisor_repo, monkeypatch):
    monkeypatch.setattr(api_main, "ADVISOR_REPO", advisor_repo)
    enricher = FakeEnricher({"NVDA": 123.0})
    monkeypatch.setattr(advisor_api, "_enricher", enricher)
    return async_client


async def test_api_strategy(api):
    resp = await api.put(
        "/api/advisor/strategy",
        json={"rules": "  No penny stocks  ", "watchlist": ["$nvda", "nvda", "amd"]},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["watchlist"] == ["NVDA", "AMD"]

    resp = await api.get("/api/advisor/strategy", headers=HEADERS)
    assert resp.json()["rules"] == "No penny stocks"
    assert resp.json()["available_cash"] is None

    resp = await api.put(
        "/api/advisor/strategy",
        json={"rules": "", "available_cash": 2500, "cash_currency": "eur"},
        headers=HEADERS,
    )
    assert resp.json()["available_cash"] == 2500
    assert resp.json()["cash_currency"] == "EUR"

    resp = await api.put(
        "/api/advisor/strategy", json={"available_cash": -1}, headers=HEADERS
    )
    assert resp.status_code == 422


async def test_api_requires_the_key(api):
    resp = await api.get("/api/advisor/strategy")
    assert resp.status_code == 401


async def test_api_log_and_list_calls(api):
    resp = await api.post(
        "/api/advisor/calls",
        json={
            "symbol": "$nvda",
            "action": "BUY",
            "reasoning": "Sentiment flipped bullish",
            "conviction": "Medium",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["symbol"] == "NVDA"
    assert body["action"] == "buy"
    assert body["conviction"] == "medium"
    assert body["price_at_call"] == 123.0  # priced by the server

    # The server can't price it, so the caller's price is used.
    resp = await api.post(
        "/api/advisor/calls",
        json={"symbol": "XYZ", "action": "watch", "reasoning": "r", "price": 4.5},
        headers=HEADERS,
    )
    assert resp.json()["price_at_call"] == 4.5

    for bad in (
        {"symbol": "NVDA", "action": "yolo", "reasoning": "r"},
        {"symbol": "not a ticker", "action": "buy", "reasoning": "r"},
        {"symbol": "NVDA", "action": "buy", "reasoning": "r", "conviction": "max"},
        {"symbol": "NVDA", "action": "buy", "reasoning": ""},
    ):
        resp = await api.post("/api/advisor/calls", json=bad, headers=HEADERS)
        assert resp.status_code == 422, bad

    calls = (await api.get("/api/advisor/calls", headers=HEADERS)).json()
    assert [c["symbol"] for c in calls] == ["XYZ", "NVDA"]

    card = (await api.get("/api/advisor/scorecard", headers=HEADERS)).json()
    assert card["total_calls"] == 2
