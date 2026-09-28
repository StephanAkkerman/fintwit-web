"""Tests for the Reddit trend integration (issue #6).

`reddit-stock-analyzer` is not in the `[test]` extra — it pulls torch — so the
analyzer is faked at the service boundary throughout. That is also what the
production code has to cope with: a deployment without the package installed.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.infra.repos import _epoch_to_naive_utc
from app.runtime.reddit_trends import (
    capture_trends,
    reset_status,
    run_reddit_trends,
    worker_status,
)
from app.services import reddit_trends_service as service

#: A fixed instant, for asserting on the epoch conversion itself.
FIXED_EPOCH = 1705320000.0  # 2024-01-15 12:00:00 UTC


def now_epoch() -> float:
    """Reports are stored against the wall clock, and the history queries
    filter on a rolling cutoff — so fixtures have to be clock-relative or they
    age out of every window."""
    return datetime.now(timezone.utc).timestamp()


def make_report(**overrides) -> dict:
    """A `TrendReport.to_dict()` payload, shaped as the package emits it."""
    now = now_epoch()
    report = {
        "generated_at": now,
        "window_hours": 24.0,
        "baseline_hours": 24.0,
        "window_start": now - 86400,
        "baseline_start": now - 172800,
        "subreddits": ["wallstreetbets", "stocks"],
        "posts_analyzed": 120,
        "posts_in_window": 80,
        "mood": "bullish",
        "sentiment_score": 0.21,
        "sentiment_breakdown": {"bullish": 50, "neutral": 20, "bearish": 10},
        "rising": ["NVDA"],
        "fading": ["AMC"],
        "emerging": ["RKLB"],
        "by_subreddit": [{"subreddit": "wallstreetbets", "posts": 60}],
        "timeline": {"bucket_seconds": 3600, "series": {"NVDA": [1, 2, 3]}},
        "tickers": [
            {
                "symbol": "NVDA",
                "mentions": 41,
                "previous_mentions": 18,
                "unique_authors": 33,
                "score_sum": 900,
                "comment_sum": 210,
                "engagement": 1320,
                "mentions_per_hour": 1.7083,
                "momentum": 1.21,
                "change_ratio": 2.28,
                "spike_score": 2.84,
                "heat_score": 0.912,
                "sentiment": "bullish",
                "sentiment_score": 0.44,
                "sentiment_breakdown": {"bullish": 30, "bearish": 5},
                "is_emerging": False,
                "subreddits": {"wallstreetbets": 30, "stocks": 11},
                "sample_posts": [{"id": "abc", "title": "NVDA to the moon"}],
            },
            {
                "symbol": "INTC",
                "mentions": 9,
                "previous_mentions": 12,
                "unique_authors": 8,
                "score_sum": 40,
                "comment_sum": 15,
                "engagement": 70,
                "mentions_per_hour": 0.375,
                "momentum": -0.23,
                "change_ratio": 0.75,
                "spike_score": -0.4,
                "heat_score": 0.21,
                "sentiment": "bearish",
                "sentiment_score": -0.51,
                "sentiment_breakdown": {"bearish": 7},
                "is_emerging": False,
                "subreddits": {"stocks": 9},
                "sample_posts": [],
            },
        ],
    }
    report.update(overrides)
    return report


@pytest.fixture(autouse=True)
def _reset_service():
    service.reset_service()
    yield
    service.reset_service()


class TestRepo:
    @pytest.mark.asyncio
    async def test_save_and_read_back_a_run(self, reddit_trend_repo):
        await reddit_trend_repo.save_report(make_report())

        run = await reddit_trend_repo.latest_run()
        assert run["posts_analyzed"] == 120
        assert run["mood"] == "bullish"
        assert run["subreddits"] == ["wallstreetbets", "stocks"]
        assert run["rising"] == ["NVDA"]
        assert [t["symbol"] for t in run["tickers"]] == ["NVDA", "INTC"]

    @pytest.mark.asyncio
    async def test_ranking_order_is_preserved(self, reddit_trend_repo):
        # The report arrives ranked by heat_score; rank is stored so the API
        # does not have to re-sort (or re-derive) it.
        await reddit_trend_repo.save_report(make_report())

        run = await reddit_trend_repo.latest_run()
        assert [t["rank"] for t in run["tickers"]] == [0, 1]

    @pytest.mark.asyncio
    async def test_per_ticker_metrics_round_trip(self, reddit_trend_repo):
        await reddit_trend_repo.save_report(make_report())

        run = await reddit_trend_repo.latest_run()
        nvda = run["tickers"][0]
        assert nvda["mentions"] == 41
        assert nvda["previous_mentions"] == 18
        assert nvda["momentum"] == pytest.approx(1.21)
        assert nvda["spike_score"] == pytest.approx(2.84)
        assert nvda["subreddits"] == {"wallstreetbets": 30, "stocks": 11}
        assert nvda["sample_posts"][0]["title"] == "NVDA to the moon"

    @pytest.mark.asyncio
    async def test_bearish_ticker_keeps_its_sign(self, reddit_trend_repo):
        await reddit_trend_repo.save_report(make_report())

        run = await reddit_trend_repo.latest_run()
        intc = run["tickers"][1]
        assert intc["sentiment"] == "bearish"
        assert intc["sentiment_score"] < 0

    @pytest.mark.asyncio
    async def test_latest_run_returns_the_newest(self, reddit_trend_repo):
        await reddit_trend_repo.save_report(
            make_report(generated_at=now_epoch() - 3600, posts_analyzed=1)
        )
        await reddit_trend_repo.save_report(make_report(posts_analyzed=2))

        run = await reddit_trend_repo.latest_run()
        assert run["posts_analyzed"] == 2

    @pytest.mark.asyncio
    async def test_limit_truncates_the_ranking(self, reddit_trend_repo):
        await reddit_trend_repo.save_report(make_report())

        run = await reddit_trend_repo.latest_run(limit=1)
        assert [t["symbol"] for t in run["tickers"]] == ["NVDA"]

    @pytest.mark.asyncio
    async def test_no_runs_reads_as_none(self, reddit_trend_repo):
        assert await reddit_trend_repo.latest_run() is None

    @pytest.mark.asyncio
    async def test_ticker_history_is_oldest_first(self, reddit_trend_repo):
        base = now_epoch() - 7200
        for offset, mentions in ((0, 10), (3600, 20), (7200, 30)):
            report = make_report(generated_at=base + offset)
            report["tickers"][0]["mentions"] = mentions
            await reddit_trend_repo.save_report(report)

        history = await reddit_trend_repo.ticker_history("NVDA", days=30)
        assert [p["mentions"] for p in history] == [10, 20, 30]

    @pytest.mark.asyncio
    async def test_ticker_history_is_case_insensitive(self, reddit_trend_repo):
        await reddit_trend_repo.save_report(make_report())

        assert len(await reddit_trend_repo.ticker_history("nvda")) == 1

    @pytest.mark.asyncio
    async def test_ticker_history_respects_the_cutoff(self, reddit_trend_repo):
        old = (datetime.now(timezone.utc) - timedelta(days=60)).timestamp()
        await reddit_trend_repo.save_report(make_report(generated_at=old))
        await reddit_trend_repo.save_report(make_report())

        assert len(await reddit_trend_repo.ticker_history("NVDA", days=30)) == 1

    @pytest.mark.asyncio
    async def test_prune_drops_old_runs_and_their_tickers(self, reddit_trend_repo):
        old = (datetime.now(timezone.utc) - timedelta(days=200)).timestamp()
        await reddit_trend_repo.save_report(make_report(generated_at=old))
        await reddit_trend_repo.save_report(make_report())

        assert await reddit_trend_repo.prune(keep_days=90) == 1
        assert len(await reddit_trend_repo.ticker_history("NVDA", days=365)) == 1

    @pytest.mark.asyncio
    async def test_prune_with_nothing_stale(self, reddit_trend_repo):
        await reddit_trend_repo.save_report(make_report())
        assert await reddit_trend_repo.prune(keep_days=90) == 0

    @pytest.mark.asyncio
    async def test_a_report_with_no_tickers_still_stores_the_run(
        self, reddit_trend_repo
    ):
        await reddit_trend_repo.save_report(make_report(tickers=[]))

        run = await reddit_trend_repo.latest_run()
        assert run["tickers"] == []
        assert run["posts_analyzed"] == 120


def test_epoch_conversion_handles_junk():
    # `generated_at` comes from outside this codebase; a bad value must not
    # take down a whole scrape's worth of work at the point of storing it.
    assert _epoch_to_naive_utc(FIXED_EPOCH) == datetime(2024, 1, 15, 12, 0, 0)
    assert isinstance(_epoch_to_naive_utc(None), datetime)
    assert isinstance(_epoch_to_naive_utc("not-a-number"), datetime)


class TestWorker:
    @pytest.mark.asyncio
    async def test_capture_stores_the_report(self, reddit_trend_repo):
        with patch.object(
            service, "fetch_trend_report", AsyncMock(return_value=make_report())
        ):
            with patch(
                "app.runtime.reddit_trends.fetch_trend_report",
                AsyncMock(return_value=make_report()),
            ):
                report = await capture_trends(reddit_trend_repo)

        assert report is not None
        run = await reddit_trend_repo.latest_run()
        assert run["posts_analyzed"] == 120

    @pytest.mark.asyncio
    async def test_an_empty_scrape_is_not_stored(self, reddit_trend_repo):
        # Every subreddit request failing must not write a run that would then
        # read as "nobody is talking about anything".
        with patch(
            "app.runtime.reddit_trends.fetch_trend_report",
            AsyncMock(return_value=make_report(posts_analyzed=0, tickers=[])),
        ):
            assert await capture_trends(reddit_trend_repo) is None

        assert await reddit_trend_repo.latest_run() is None

    @pytest.mark.asyncio
    async def test_worker_stops_when_the_package_is_missing(self, reddit_trend_repo):
        # No point retrying on an interval: an import does not start working
        # mid-process.
        with (
            patch("app.runtime.reddit_trends.warmup", AsyncMock()),
            patch(
                "app.runtime.reddit_trends.fetch_trend_report",
                AsyncMock(side_effect=service.RedditAnalyzerUnavailable("nope")),
            ),
        ):
            await run_reddit_trends(reddit_trend_repo, interval=1)

        assert await reddit_trend_repo.latest_run() is None

    @pytest.mark.asyncio
    async def test_worker_skips_when_a_recent_run_exists(self, reddit_trend_repo):
        await reddit_trend_repo.save_report(make_report())
        fetch = AsyncMock(side_effect=service.RedditAnalyzerUnavailable("stop"))

        with (
            patch("app.runtime.reddit_trends.warmup", AsyncMock()),
            patch("app.runtime.reddit_trends.fetch_trend_report", fetch),
            patch(
                "app.runtime.reddit_trends.asyncio.sleep",
                AsyncMock(side_effect=StopAsyncIteration),
            ),
        ):
            with pytest.raises(StopAsyncIteration):
                await run_reddit_trends(reddit_trend_repo, interval=3600)

        # It reached the sleep without scraping, because a run is fresh.
        fetch.assert_not_awaited()


class TestWorkerStatus:
    """The worker reports what it is doing, so a scrape that keeps failing
    surfaces its error on the page instead of reading as "not scraped yet"."""

    @pytest.fixture(autouse=True)
    def _fresh_status(self):
        reset_status()
        yield
        reset_status()

    @staticmethod
    async def _one_pass(repo, fetch):
        """Run the worker until its first sleep, then stop it."""
        with (
            patch("app.runtime.reddit_trends.warmup", AsyncMock()),
            patch("app.runtime.reddit_trends.fetch_trend_report", fetch),
            patch(
                "app.runtime.reddit_trends.asyncio.sleep",
                AsyncMock(side_effect=StopAsyncIteration),
            ),
        ):
            with pytest.raises(StopAsyncIteration):
                await run_reddit_trends(repo, interval=900)

    def test_starts_idle(self):
        status = worker_status()
        assert status["state"] == "idle"
        assert status["last_error"] is None

    @pytest.mark.asyncio
    async def test_a_successful_pass_reads_ok(self, reddit_trend_repo):
        await self._one_pass(reddit_trend_repo, AsyncMock(return_value=make_report()))

        status = worker_status()
        assert status["state"] == "ok"
        assert status["last_success_at"] is not None
        assert status["last_posts_analyzed"] == 120
        assert status["next_attempt_at"] is not None

    @pytest.mark.asyncio
    async def test_a_failing_pass_records_the_error(self, reddit_trend_repo):
        fetch = AsyncMock(side_effect=ImportError("gliner2 needs transformers<5"))
        await self._one_pass(reddit_trend_repo, fetch)

        status = worker_status()
        assert status["state"] == "error"
        assert "gliner2 needs transformers<5" in status["last_error"]
        assert status["last_attempt_at"] is not None
        assert status["last_success_at"] is None

    @pytest.mark.asyncio
    async def test_an_empty_scrape_says_reddit_returned_nothing(
        self, reddit_trend_repo
    ):
        fetch = AsyncMock(return_value=make_report(posts_analyzed=0, tickers=[]))
        await self._one_pass(reddit_trend_repo, fetch)

        status = worker_status()
        assert status["state"] == "empty"
        assert "REDDIT_CLIENT_ID" in status["last_error"]

    @pytest.mark.asyncio
    async def test_a_missing_package_reads_unavailable(self, reddit_trend_repo):
        with (
            patch("app.runtime.reddit_trends.warmup", AsyncMock()),
            patch(
                "app.runtime.reddit_trends.fetch_trend_report",
                AsyncMock(side_effect=service.RedditAnalyzerUnavailable("nope")),
            ),
        ):
            await run_reddit_trends(reddit_trend_repo, interval=1)

        assert worker_status()["state"] == "unavailable"

    def test_status_is_a_copy(self):
        worker_status()["state"] = "tampered"
        assert worker_status()["state"] == "idle"


class TestServiceAvailability:
    def test_unavailable_without_the_package(self):
        with patch.dict("sys.modules", {"reddit_stock_analyzer": None}):
            assert service.is_available() is False

    def test_default_subreddits_survive_a_missing_package(self, monkeypatch):
        monkeypatch.delenv("REDDIT_SUBREDDITS", raising=False)
        with patch.dict("sys.modules", {"reddit_stock_analyzer": None}):
            names = service.default_subreddits()
        assert "wallstreetbets" in names

    def test_env_override_wins(self, monkeypatch):
        monkeypatch.setenv("REDDIT_SUBREDDITS", "stocks, options ,")
        assert service.default_subreddits() == ["stocks", "options"]

    def test_categories_are_empty_without_the_package(self):
        with patch.dict("sys.modules", {"reddit_stock_analyzer": None}):
            assert service.subreddit_categories() == {}

    def test_resolve_prefers_an_explicit_list(self):
        assert service.resolve_subreddits(["wallstreetbets"]) == ["wallstreetbets"]


class FakeTrendReport:
    """Stands in for the package's TrendReport dataclass."""

    def __init__(self, payload: dict):
        self._payload = payload
        self.tickers = payload["tickers"]
        self.posts_analyzed = payload["posts_analyzed"]

    def to_dict(self) -> dict:
        return self._payload


class FakeAnalyzer:
    def __init__(self):
        self.warmed = False

    def warm_up(self):
        self.warmed = True


class FakeRedditTrendService:
    """Records how the adapter calls the package."""

    def __init__(self, client=None, **kwargs):
        self.client = client
        self.analyzer = FakeAnalyzer()
        self.trend_calls: list[dict] = []
        self.overview_calls: list[dict] = []
        self.closed = False

    async def trend_report(self, subreddits=None, **kwargs):
        self.trend_calls.append({"subreddits": list(subreddits or []), **kwargs})
        return FakeTrendReport(make_report())

    async def subreddit_overview(self, subreddit, **kwargs):
        self.overview_calls.append({"subreddit": subreddit, **kwargs})
        return {"subreddit": subreddit, "sample_size": 3, "top_tickers": {"NVDA": 2}}

    async def close(self):
        self.closed = True


def fake_package(monkeypatch):
    """Install a stand-in `reddit_stock_analyzer` module.

    The real package is not installed here — it pulls torch, so it is kept out
    of the `[test]` extra — but the adapter's contract with it (which names it
    imports, which arguments it passes) is exactly what needs pinning down.
    """
    import sys
    import types

    module = types.ModuleType("reddit_stock_analyzer")
    module.RedditClient = lambda *a, **k: "client"
    module.RedditTrendService = FakeRedditTrendService
    module.DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks")
    module.SUBREDDIT_CATEGORIES = {"retail": ("wallstreetbets",)}
    module.subreddits_for = lambda category: ("wallstreetbets",)
    monkeypatch.setitem(sys.modules, "reddit_stock_analyzer", module)
    return module


class TestServiceDelegation:
    @pytest.mark.asyncio
    async def test_fetch_trend_report_passes_the_window_through(self, monkeypatch):
        fake_package(monkeypatch)

        report = await service.fetch_trend_report(
            ["wallstreetbets"], window_hours=12.0, limit=30, top_n=5
        )

        assert report["posts_analyzed"] == 120
        call = service._load_service().trend_calls[0]
        assert call["subreddits"] == ["wallstreetbets"]
        assert call["window_hours"] == 12.0
        assert call["limit"] == 30
        assert call["top_n"] == 5

    @pytest.mark.asyncio
    async def test_the_service_is_built_once(self, monkeypatch):
        fake_package(monkeypatch)

        await service.fetch_trend_report(["stocks"])
        await service.fetch_trend_report(["stocks"])

        # Loading market data and two models per call would be the whole cost
        # of the feature, paid every time.
        assert len(service._load_service().trend_calls) == 2

    @pytest.mark.asyncio
    async def test_falls_back_to_the_default_subreddits(self, monkeypatch):
        monkeypatch.delenv("REDDIT_SUBREDDITS", raising=False)
        fake_package(monkeypatch)

        await service.fetch_trend_report()

        assert service._load_service().trend_calls[0]["subreddits"] == [
            "wallstreetbets",
            "stocks",
        ]

    @pytest.mark.asyncio
    async def test_subreddit_summary_delegates(self, monkeypatch):
        fake_package(monkeypatch)

        summary = await service.fetch_subreddit_summary("wallstreetbets", limit=20)

        assert summary["top_tickers"] == {"NVDA": 2}
        assert service._load_service().overview_calls[0]["limit"] == 20

    @pytest.mark.asyncio
    async def test_warmup_loads_the_models(self, monkeypatch):
        fake_package(monkeypatch)

        await service.warmup()

        assert service._load_service().analyzer.warmed is True

    @pytest.mark.asyncio
    async def test_warmup_is_a_noop_without_the_package(self):
        from unittest.mock import patch as _patch

        with _patch.dict("sys.modules", {"reddit_stock_analyzer": None}):
            await service.warmup()  # must not raise

    @pytest.mark.asyncio
    async def test_close_releases_the_session(self, monkeypatch):
        fake_package(monkeypatch)
        await service.fetch_trend_report(["stocks"])
        built = service._load_service()

        await service.close()

        assert built.closed is True

    def test_resolve_by_category(self, monkeypatch):
        fake_package(monkeypatch)
        assert service.resolve_subreddits(category="retail") == ["wallstreetbets"]

    def test_categories_come_from_the_package(self, monkeypatch):
        fake_package(monkeypatch)
        assert service.subreddit_categories() == {"retail": ["wallstreetbets"]}
