import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infra.db import Base, TraderCallRow
from app.infra.repos import TraderCallRepo
from app.runtime.trader_evaluator import evaluate_due_calls

pytestmark = pytest.mark.asyncio


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
async def Session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def repo(Session):
    return TraderCallRepo(Session)


async def _insert_call(Session, **overrides):
    defaults = dict(
        tweet_id=1,
        ticker="AAPL",
        user_screen_name="alice",
        direction="bullish",
        sentiment_score=0.5,
        asset_kind="EQUITY",
        price_at_call=100.0,
        called_at=_now() - timedelta(days=2),
        created_at=_now() - timedelta(days=2),
    )
    defaults.update(overrides)
    async with Session() as s:
        async with s.begin():
            s.add(TraderCallRow(**defaults))


class _FakeEnricher:
    def __init__(self, prices: dict[str, float]):
        self.prices = prices
        self.calls: list[list[str]] = []

    async def classify(self, tickers):
        self.calls.append(list(tickers))
        return [
            {"symbol": t, "financials": {"price": self.prices[t]}}
            for t in tickers
            if t in self.prices
        ]


async def test_evaluate_due_calls_grades_bullish_win(Session, repo):
    await _insert_call(Session, ticker="AAPL", price_at_call=100.0)
    enricher = _FakeEnricher({"AAPL": 110.0})

    graded = await evaluate_due_calls(Session, repo, enricher)

    assert graded == 1


async def test_evaluate_due_calls_writes_result_row(Session, repo):
    await _insert_call(Session, ticker="AAPL", price_at_call=100.0, direction="bullish")
    enricher = _FakeEnricher({"AAPL": 110.0})

    await evaluate_due_calls(Session, repo, enricher)

    async with Session() as s:
        from sqlalchemy import select

        from app.infra.db import TraderCallResultRow

        rows = (await s.execute(select(TraderCallResultRow))).scalars().all()

    assert len(rows) == 1
    assert rows[0].correct is True
    assert rows[0].return_pct == pytest.approx(10.0)
    assert rows[0].horizon_days == 1


async def test_evaluate_due_calls_skips_when_price_unavailable(Session, repo):
    await _insert_call(Session, ticker="AAPL", price_at_call=100.0)
    enricher = _FakeEnricher({})  # no price for AAPL

    graded = await evaluate_due_calls(Session, repo, enricher)

    assert graded == 0


async def test_evaluate_due_calls_ignores_calls_not_yet_due(Session, repo):
    await _insert_call(
        Session,
        ticker="AAPL",
        price_at_call=100.0,
        called_at=_now() - timedelta(hours=1),
        created_at=_now() - timedelta(hours=1),
    )
    enricher = _FakeEnricher({"AAPL": 200.0})

    graded = await evaluate_due_calls(Session, repo, enricher)

    assert graded == 0
    assert enricher.calls == []


async def test_evaluate_due_calls_is_idempotent(Session, repo):
    await _insert_call(Session, ticker="AAPL", price_at_call=100.0)
    enricher = _FakeEnricher({"AAPL": 110.0})

    first = await evaluate_due_calls(Session, repo, enricher)
    second = await evaluate_due_calls(Session, repo, enricher)

    assert first == 1
    assert second == 0  # already graded at horizon=1, not due again
