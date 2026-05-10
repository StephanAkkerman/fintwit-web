# Timeframe-Anchored Price Direction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `AVG(change_percent)` in `get_mention_heat` with a point-to-point percentage return calculated from `financials.price` in tweet assets, anchored to the selected window boundary.

**Architecture:** A 3-CTE SQL query replaces the existing flat query inside `get_mention_heat`. Two price CTEs (`price_recent`, `price_at_start`) use `ROW_NUMBER()` window functions to find the most recent tweet price and the tweet price closest to `now − window_hours` for each ticker. A `mentions` CTE preserves the existing aggregation logic. The final SELECT LEFT JOINs all three and computes `(price_now − price_then) / price_then * 100`.

**Tech Stack:** Python 3.10+, SQLAlchemy async, SQLite (3.25+ for window functions), pytest-asyncio

---

## File Map

| Action | File |
|--------|------|
| Modify | `app/services/mention_aggregator.py` — `get_mention_heat` only |
| Modify | `tests/test_mention_aggregator.py` — fix pre-existing issues + new price tests |

---

### Task 1: Fix pre-existing test issues and add failing price direction tests

The existing test file has two bugs unrelated to this feature that would cause CI failures:
1. `get_mention_heat` is called with `min_mentions=N` which the function doesn't accept yet
2. Tests assert `row["mentions_24h"]` but the function returns `row["mentions"]`

Fix both, add `price` to the `_tweet` helper, and add four failing price direction tests.

**Files:**
- Modify: `tests/test_mention_aggregator.py`

- [ ] **Step 1: Update `_tweet` helper and fix test assertions**

Replace the `_tweet` helper and the three existing `get_mention_heat` test functions in `tests/test_mention_aggregator.py`:

```python
import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infra.db import Base, TweetRow

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def Session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _tweet(id, tickers, label, score, hours_ago, kind="EQUITY", change_pct=0.0, price=None):
    financials = {"change_percent": change_pct}
    if price is not None:
        financials["price"] = price
    return TweetRow(
        id=id, text="x", user_name="u", user_screen_name="u", user_img="",
        url="", media=[], tickers=tickers, hashtags=[], title="",
        media_types=[], created_at=_now() - timedelta(hours=hours_ago),
        sentiment_label=label, sentiment_score=score,
        assets=[{"symbol": t, "kind": kind, "financials": financials} for t in tickers],
        is_options_tweet=False,
    )


async def _insert(Session, rows):
    async with Session() as s:
        async with s.begin():
            for r in rows:
                s.add(r)


async def test_mention_heat_counts(Session):
    from app.services.mention_aggregator import get_mention_heat

    await _insert(Session, [
        _tweet(1, ["BTC"], "BULL", 0.8, 1, "CRYPTO"),
        _tweet(2, ["BTC"], "BULL", 0.6, 3, "CRYPTO"),
        _tweet(3, ["AAPL"], "BEAR", -0.7, 2, "EQUITY"),
    ])

    rows = await get_mention_heat(Session, min_mentions=1)
    btc = next(r for r in rows if r["ticker"] == "BTC")

    assert btc["mentions"] == 2
    assert btc["asset_kind"] == "CRYPTO"
    assert btc["sentiment_label_24h"] == "BULL"


async def test_mention_heat_avg_sentiment(Session):
    from app.services.mention_aggregator import get_mention_heat

    await _insert(Session, [
        _tweet(1, ["BTC"], "BULL", 0.8, 1, "CRYPTO"),
        _tweet(2, ["BTC"], "BULL", 0.4, 2, "CRYPTO"),
    ])

    rows = await get_mention_heat(Session, min_mentions=1)
    btc = next(r for r in rows if r["ticker"] == "BTC")

    assert abs(btc["avg_sentiment_24h"] - 0.6) < 0.01


async def test_mention_heat_min_mentions_filter(Session):
    from app.services.mention_aggregator import get_mention_heat

    await _insert(Session, [
        _tweet(1, ["BIG"], "BULL", 0.5, 1),
        _tweet(2, ["BIG"], "BULL", 0.5, 2),
        _tweet(3, ["TINY"], "BULL", 0.5, 1),
    ])

    rows = await get_mention_heat(Session, min_mentions=2)
    tickers = [r["ticker"] for r in rows]
    assert "BIG" in tickers
    assert "TINY" not in tickers


async def test_volume_baseline_multiplier(Session):
    from app.services.mention_aggregator import get_volume_baseline

    tweets = [_tweet(i, ["GME"], "NEUTRAL", 0.0, i * 0.5) for i in range(1, 8)]
    tweets += [_tweet(i + 10, ["GME"], "NEUTRAL", 0.0, i * 24) for i in range(1, 7)]
    await _insert(Session, tweets)

    rows = await get_volume_baseline(Session, threshold=2.0)
    gme = next((r for r in rows if r["ticker"] == "GME"), None)
    assert gme is not None
    assert gme["volume_multiplier"] > 2.0


async def test_sentiment_shift_detects_swing(Session):
    from app.services.mention_aggregator import get_sentiment_shift

    await _insert(Session, [
        _tweet(1, ["ETH"], "BULL", 0.7, 2),
        _tweet(2, ["ETH"], "BEAR", -0.5, 30),
    ])

    rows = await get_sentiment_shift(Session)
    eth = next((r for r in rows if r["ticker"] == "ETH"), None)
    assert eth is not None
    assert eth["sentiment_label_24h"] == "BULL"
    assert eth["sentiment_label_prev"] == "BEAR"


async def test_hidden_gems_detects_new(Session):
    from app.services.mention_aggregator import get_hidden_gems

    await _insert(Session, [_tweet(1, ["NEWCO"], "BULL", 0.5, 0.5)])

    rows = await get_hidden_gems(Session)
    gem = next((r for r in rows if r["ticker"] == "NEWCO"), None)
    assert gem is not None
    assert gem["gem_subtype"] == "new"


async def test_hidden_gems_detects_resurfacing(Session):
    from app.services.mention_aggregator import get_hidden_gems

    await _insert(Session, [
        _tweet(1, ["OLD"], "BULL", 0.5, 0.5),
        _tweet(2, ["OLD"], "BULL", 0.5, 24 * 10),
    ])

    rows = await get_hidden_gems(Session)
    gem = next((r for r in rows if r["ticker"] == "OLD"), None)
    assert gem is not None
    assert gem["gem_subtype"] == "resurfacing"
    assert gem["days_since_last"] is not None and gem["days_since_last"] >= 9


# ── New: price direction tests (will FAIL until Task 2 is implemented) ─────

async def test_price_direction_rising(Session):
    """24h window: price up 10% → price_direction ≈ +10."""
    from app.services.mention_aggregator import get_mention_heat

    await _insert(Session, [
        # Outside 24h window but closest to the 24h cutoff → price_then
        _tweet(10, ["BTC"], "BULL", 0.5, 25, kind="CRYPTO", price=100.0),
        # Inside 24h window, most recent → price_now
        _tweet(11, ["BTC"], "BULL", 0.5,  1, kind="CRYPTO", price=110.0),
    ])

    rows = await get_mention_heat(Session, window_hours=24)
    btc = next(r for r in rows if r["ticker"] == "BTC")
    assert btc["price_direction"] == pytest.approx(10.0, abs=0.5)


async def test_price_direction_falling(Session):
    """24h window: price down 10% → price_direction ≈ -10."""
    from app.services.mention_aggregator import get_mention_heat

    await _insert(Session, [
        _tweet(20, ["ETH"], "BEAR", -0.5, 25, kind="CRYPTO", price=200.0),
        _tweet(21, ["ETH"], "BEAR", -0.5,  1, kind="CRYPTO", price=180.0),
    ])

    rows = await get_mention_heat(Session, window_hours=24)
    eth = next(r for r in rows if r["ticker"] == "ETH")
    assert eth["price_direction"] == pytest.approx(-10.0, abs=0.5)


async def test_price_direction_null_without_price(Session):
    """Ticker with no financials.price → price_direction is None."""
    from app.services.mention_aggregator import get_mention_heat

    await _insert(Session, [
        _tweet(30, ["NOPX"], "NEUTRAL", 0.0, 1),  # no price kwarg → no price in assets
    ])

    rows = await get_mention_heat(Session, window_hours=24)
    item = next((r for r in rows if r["ticker"] == "NOPX"), None)
    assert item is not None
    assert item["price_direction"] is None


async def test_price_direction_7d_window(Session):
    """168h window: tweet at 170h ago as price_then, 1h ago as price_now → +10%."""
    from app.services.mention_aggregator import get_mention_heat

    await _insert(Session, [
        # ~7d ago (170h) — outside 168h window, closest to cutoff → price_then
        _tweet(40, ["SPY"], "BULL", 0.5, 170, price=400.0),
        # 1h ago — inside 168h window, most recent → price_now
        _tweet(41, ["SPY"], "BULL", 0.5,   1, price=440.0),
    ])

    rows = await get_mention_heat(Session, window_hours=168)
    spy = next((r for r in rows if r["ticker"] == "SPY"), None)
    assert spy is not None
    assert spy["price_direction"] == pytest.approx(10.0, abs=0.5)
```

- [ ] **Step 2: Run existing tests to confirm pre-existing failures are visible**

```
pytest tests/test_mention_aggregator.py -v 2>&1 | head -60
```

Expected: `test_mention_heat_counts` FAILS (`KeyError: 'mentions_24h'`), `test_mention_heat_min_mentions_filter` FAILS (`unexpected keyword argument 'min_mentions'`), new price direction tests FAIL.

- [ ] **Step 3: Commit the updated test file**

```bash
git add tests/test_mention_aggregator.py
git commit -m "test: fix mention aggregator test assertions and add price direction tests"
```

---

### Task 2: Implement the 3-CTE query in `get_mention_heat`

Replace the flat SQL query with the CTE version. Add `min_mentions` parameter. No other functions in the file change.

**Files:**
- Modify: `app/services/mention_aggregator.py`

- [ ] **Step 1: Replace `get_mention_heat` with the CTE implementation**

Replace the entire `get_mention_heat` function in `app/services/mention_aggregator.py` (lines 43–86) with:

```python
async def get_mention_heat(
    Session: async_sessionmaker,
    asset_kind: str = "all",
    window_hours: int = 24,
    limit: int = 50,
    min_mentions: int = 1,
) -> list[dict]:
    now = _now()
    cutoff = now - timedelta(hours=window_hours)
    kind_clause = _KIND_FILTER.get(asset_kind.upper(), "")

    sql = text(f"""
        WITH
        price_recent AS (
            SELECT
                j.value AS ticker,
                json_extract(ae.value, '$.financials.price') AS price,
                ROW_NUMBER() OVER (
                    PARTITION BY j.value
                    ORDER BY t.created_at DESC
                ) AS rn
            FROM tweets t, json_each(t.tickers) j
            LEFT JOIN json_each(t.assets) ae
                   ON json_extract(ae.value, '$.symbol') = j.value
            WHERE json_extract(ae.value, '$.financials.price') IS NOT NULL
              AND t.tickers IS NOT NULL AND t.tickers != '[]'
        ),
        price_at_start AS (
            SELECT
                j.value AS ticker,
                json_extract(ae.value, '$.financials.price') AS price,
                ROW_NUMBER() OVER (
                    PARTITION BY j.value
                    ORDER BY ABS(julianday(t.created_at) - julianday(:cutoff))
                ) AS rn
            FROM tweets t, json_each(t.tickers) j
            LEFT JOIN json_each(t.assets) ae
                   ON json_extract(ae.value, '$.symbol') = j.value
            WHERE json_extract(ae.value, '$.financials.price') IS NOT NULL
              AND t.tickers IS NOT NULL AND t.tickers != '[]'
        ),
        mentions AS (
            SELECT
                j.value AS ticker,
                CAST(COUNT(*) AS INTEGER) AS mentions,
                AVG(t.sentiment_score) AS avg_sentiment_24h,
                MAX(json_extract(ae.value, '$.kind')) AS asset_kind
            FROM tweets t, json_each(t.tickers) j
            LEFT JOIN json_each(t.assets) ae
                   ON json_extract(ae.value, '$.symbol') = j.value
            WHERE t.created_at >= :cutoff
              AND t.tickers IS NOT NULL AND t.tickers != '[]'
            GROUP BY j.value
            HAVING COUNT(*) >= :min_mentions
            {kind_clause}
        )
        SELECT
            m.ticker,
            m.mentions,
            m.avg_sentiment_24h,
            m.asset_kind,
            CASE
                WHEN pr.price IS NOT NULL
                 AND ps.price IS NOT NULL
                 AND ps.price != 0
                THEN (pr.price - ps.price) / ps.price * 100.0
                ELSE NULL
            END AS price_direction
        FROM mentions m
        LEFT JOIN (SELECT ticker, price FROM price_recent  WHERE rn = 1) pr ON pr.ticker = m.ticker
        LEFT JOIN (SELECT ticker, price FROM price_at_start WHERE rn = 1) ps ON ps.ticker = m.ticker
        ORDER BY m.mentions DESC
        LIMIT :limit
    """)

    async with Session() as s:
        result = await s.execute(sql, {
            "cutoff": cutoff,
            "limit": limit,
            "min_mentions": min_mentions,
        })
        rows = result.mappings().all()

    return [
        {
            "ticker": r["ticker"],
            "mentions": r["mentions"],
            "avg_sentiment_24h": r["avg_sentiment_24h"] or 0.0,
            "sentiment_label_24h": _score_to_label(r["avg_sentiment_24h"]),
            "asset_kind": (r["asset_kind"] or "EQUITY").upper(),
            "price_direction": r["price_direction"],
        }
        for r in rows
    ]
```

- [ ] **Step 2: Run the full test suite for the aggregator**

```
pytest tests/test_mention_aggregator.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 3: Run the broader test suite to confirm no regressions**

```
pytest tests/ -v --ignore=tests/test_sentiment_model.py --ignore=tests/test_sentiment_backfill.py -q
```

(Sentiment model tests require GPU/model weights — skip them in CI.)

Expected: all non-model tests PASS.

- [ ] **Step 4: Commit**

```bash
git add app/services/mention_aggregator.py
git commit -m "feat: timeframe-anchored price direction in mention heat

Replace AVG(change_percent) with point-to-point % return using
financials.price from tweet assets. price_recent CTE finds the
most recent price per ticker; price_at_start CTE finds the price
closest to now-window_hours. Applies to all windows (24h/48h/168h).
Also adds min_mentions param (default 1) to get_mention_heat."
```
