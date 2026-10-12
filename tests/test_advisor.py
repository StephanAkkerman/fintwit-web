from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api import advisor as advisor_api
from app.api import main as api_main
from app.infra.db import AdvisorCallRow
from app.infra.repos import AdvisorRepo, PortfolioRepo, TweetRepo
from app.runtime.advisor_evaluator import evaluate_due_advisor_calls
from app.services.advisor import (
    build_scorecard,
    group_ticker_posts,
    normalize_screen_names,
    normalize_watchlist,
)

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


def test_normalize_screen_names():
    assert normalize_screen_names(
        ["@ShardiB2", "shardib2", " someone_1 ", "not a handle", "", "x" * 16]
    ) == ["shardib2", "someone_1"]


def _tweet(tweet_id, author, tickers, score=0.9, hours_ago=1, **extra):
    return {
        "id": tweet_id,
        "text": f"{author} on {' '.join(tickers)}",
        "user_name": author,
        "user_screen_name": author,
        "user_img": "",
        "url": f"https://x.com/{author}/status/{tweet_id}",
        "media": [],
        "tickers": tickers,
        "hashtags": [],
        "title": "",
        "media_types": [],
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None)
        - timedelta(hours=hours_ago),
        "sentiment_score": score,
        "assets": [
            {"symbol": t, "kind": "EQUITY", "financials": {"price": 25.0}}
            for t in tickers
        ],
        **extra,
    }


def test_group_ticker_posts():
    tweets = [
        _tweet(3, "ShardiB2", ["GTLB"]),
        _tweet(2, "other", ["GTLB", "NVDA"], score=0.0),
        _tweet(1, "ShardiB2", ["NVDA", "INTC"], ticker_sentiment={"INTC": -0.9}),
    ]
    leads = group_ticker_posts(tweets, held={"NVDA"}, max_posts=1)
    by_symbol = {lead["symbol"]: lead for lead in leads}

    gtlb = by_symbol["GTLB"]
    assert gtlb["mentions"] == 2
    assert gtlb["traders"] == ["ShardiB2", "other"]
    assert (gtlb["bullish"], gtlb["bearish"]) == (1, 0)  # neutral isn't counted
    assert gtlb["held"] is False
    assert gtlb["price_at_post"] == 25.0
    assert len(gtlb["posts"]) == 1
    assert gtlb["posts"][0]["url"] == "https://x.com/ShardiB2/status/3"

    assert by_symbol["NVDA"]["held"] is True
    # The per-ticker score wins over the tweet's own score.
    assert (by_symbol["INTC"]["bullish"], by_symbol["INTC"]["bearish"]) == (0, 1)
    assert leads[-1]["mentions"] == 1


def test_group_ticker_posts_puts_followed_traders_first():
    tweets = [
        _tweet(5, "crowd1", ["TSLA"], likes=900),
        _tweet(4, "crowd2", ["TSLA"]),
        _tweet(3, "crowd3", ["TSLA"]),
        _tweet(2, "ShardiB2", ["GTLB"]),
        _tweet(1, "crowd1", ["GTLB"], likes=50),
    ]
    leads = group_ticker_posts(tweets, held=set(), followed={"shardib2"}, max_posts=2)

    # One followed trader outranks three strangers.
    assert [lead["symbol"] for lead in leads] == ["GTLB", "TSLA"]
    assert leads[0]["followed_traders"] == ["ShardiB2"]
    # The followed trader's post comes first, then the most liked.
    assert [p["trader"] for p in leads[0]["posts"]] == ["ShardiB2", "crowd1"]
    assert leads[1]["posts"][0]["likes"] == 900
    assert leads[1]["trader_count"] == 3


async def test_strategy_round_trip(advisor_repo):
    assert await advisor_repo.get_strategy() == {
        "rules": "",
        "watchlist": [],
        "followed_traders": [],
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

    followed = await advisor_repo.set_strategy(
        "Max 20% per position", ["NVDA"], followed_traders=["shardib2"]
    )
    assert followed["followed_traders"] == ["shardib2"]

    again = await advisor_repo.set_strategy("Max 10%", [])
    assert again["rules"] == "Max 10%"
    assert again["watchlist"] == []
    assert again["available_cash"] is None
    assert again["cash_currency"] is None
    # Leaving followed_traders out keeps the stored list.
    assert again["followed_traders"] == ["shardib2"]


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


async def test_api_followed_mentions(api, db_engine, monkeypatch):
    Session = async_sessionmaker(db_engine, expire_on_commit=False)
    portfolio = PortfolioRepo(Session)
    monkeypatch.setattr(api_main, "PORTFOLIO_REPO", portfolio)
    monkeypatch.setattr(api_main, "Session", Session)

    resp = await api.get("/api/advisor/followed-mentions", headers=HEADERS)
    assert resp.json()["leads"] == []  # nobody followed yet

    await TweetRepo(Session).upsert_many(
        [
            _tweet(10, "ShardiB2", ["GTLB"]),
            _tweet(11, "shardib2", ["NVDA"]),
            _tweet(12, "ShardiB2", ["AMD"], hours_ago=48),  # outside the window
            _tweet(13, "stranger", ["TSLA"]),  # not followed
        ]
    )
    await portfolio.create_position(
        {"symbol": "NVDA", "quantity": 1, "avg_cost": 100, "is_active": True}
    )
    resp = await api.put(
        "/api/advisor/strategy",
        json={"rules": "", "followed_traders": ["@ShardiB2", "bad handle!"]},
        headers=HEADERS,
    )
    assert resp.json()["followed_traders"] == ["shardib2"]

    resp = await api.get(
        "/api/advisor/followed-mentions",
        params={"since_hours": 24},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["traders"] == [{"screen_name": "shardib2", "track_record_7d": None}]
    leads = {lead["symbol"]: lead for lead in body["leads"]}
    assert set(leads) == {"GTLB", "NVDA"}
    assert leads["NVDA"]["held"] is True
    assert leads["GTLB"]["held"] is False

    # Saving the form from an older client (no followed_traders) keeps them.
    resp = await api.put("/api/advisor/strategy", json={"rules": "x"}, headers=HEADERS)
    assert resp.json()["followed_traders"] == ["shardib2"]


async def test_api_unseen_posts_and_runs(api, db_engine, monkeypatch):
    Session = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(api_main, "PORTFOLIO_REPO", PortfolioRepo(Session))
    monkeypatch.setattr(api_main, "Session", Session)
    tweets = TweetRepo(Session)
    await tweets.upsert_many(
        [
            _tweet(100, "ShardiB2", ["GTLB"]),
            _tweet(101, "stranger", ["TSLA"]),
            _tweet(102, "stranger", []),  # read, but no lead
            _tweet(90, "stranger", ["AMD"], hours_ago=20),  # before the first run
        ]
    )
    await api.put(
        "/api/advisor/strategy",
        json={"rules": "", "followed_traders": ["shardib2"]},
        headers=HEADERS,
    )

    first = (await api.get("/api/advisor/unseen-posts", headers=HEADERS)).json()
    assert first["previous_cursor"] is None
    assert first["cursor"] == "102"
    assert (first["posts"], first["posts_with_tickers"]) == (3, 2)
    assert [lead["symbol"] for lead in first["leads"]] == ["GTLB", "TSLA"]
    assert first["truncated"] is False

    resp = await api.post(
        "/api/advisor/runs",
        json={
            "cursor": first["cursor"],
            "summary": "Nothing new",
            "session": "Pre-market",
            "posts_read": 3,
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201
    assert resp.json()["tweet_cursor"] == "102"

    # Nothing new yet: the cursor stays put.
    again = (await api.get("/api/advisor/unseen-posts", headers=HEADERS)).json()
    assert (again["previous_cursor"], again["cursor"], again["posts"]) == (
        "102",
        "102",
        0,
    )

    await tweets.upsert_many([_tweet(103, "stranger", ["NVDA"])])
    later = (await api.get("/api/advisor/unseen-posts", headers=HEADERS)).json()
    assert [lead["symbol"] for lead in later["leads"]] == ["NVDA"]
    assert later["cursor"] == "103"

    runs = (await api.get("/api/advisor/runs", headers=HEADERS)).json()
    assert [(r["session"], r["summary"]) for r in runs] == [
        ("Pre-market", "Nothing new")
    ]
    bad = await api.post(
        "/api/advisor/runs", json={"cursor": "abc", "summary": ""}, headers=HEADERS
    )
    assert bad.status_code == 422
