# Swing-Trader Overview Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the home route (`/`) with a swing-trader-focused overview dashboard: macro strip, mention-heat treemap, sentiment-shift leaderboard, volume-baseline widget, and hidden-gem finder — all scoped by an asset-kind filter tab.

**Architecture:** Five FastAPI endpoints under `/api/overview/` query the existing `tweets` SQLite table on-demand using SQLite's `json_each()` to unnest the `tickers` JSON array and compute aggregates in SQL. No pre-computed table or background worker needed. The macro strip reuses the existing `get_tradingview_quote` + TTL-cache pattern from `macro_market.py`. The frontend assembles seven focused components into `OverviewDashboard.tsx`, replacing the home-route widget block in `App.tsx`. Asset-kind filter state lives in `OverviewDashboard` and is passed as a prop to each child widget.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async text(), SQLite json_each; TypeScript, React 18, Tailwind CSS 3, Recharts (Treemap), Vitest + React Testing Library

---

## File Map

**New — Backend**
- `app/services/mention_aggregator.py` — SQL aggregation functions (called by router)
- `app/api/overview.py` — 5 FastAPI endpoints

**New — Frontend**
- `frontend/src/hooks/useMacroStrip.ts`
- `frontend/src/hooks/useMentionHeat.ts`
- `frontend/src/hooks/useSentimentShift.ts`
- `frontend/src/hooks/useVolumeBaseline.ts`
- `frontend/src/hooks/useHiddenGems.ts`
- `frontend/src/components/MacroStrip.tsx`
- `frontend/src/components/AssetFilterTabs.tsx`
- `frontend/src/components/MentionHeatmap.tsx`
- `frontend/src/components/SentimentShiftWidget.tsx`
- `frontend/src/components/VolumeBaselineWidget.tsx`
- `frontend/src/components/HiddenGemWidget.tsx`
- `frontend/src/components/OverviewDashboard.tsx`

**Modified**
- `app/api/main.py` — include overview router
- `frontend/src/types.ts` — add 5 new TypeScript interfaces
- `frontend/src/App.tsx` — replace home-route widget block with `<OverviewDashboard />`
- `frontend/package.json` — add `recharts` dependency

**Test files**
- `tests/test_mention_aggregator.py`
- `tests/test_overview_api.py`

---

## Task 1: Aggregator Service (SQL-based, on-demand)

**Files:**
- Create: `app/services/mention_aggregator.py`
- Create: `tests/test_mention_aggregator.py`

SQLite's `json_each(tickers)` unnests the JSON tickers array into rows. A single CTE computes per-ticker mention counts, average sentiment, and volume baseline in one pass. Hidden gems require a second query that spans the full tweet history to find global `first_seen` and `last_seen_before_24h`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mention_aggregator.py`:

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


def _tweet(id, tickers, label, score, hours_ago, kind="EQUITY", change_pct=0.0):
    return TweetRow(
        id=id, text="x", user_name="u", user_screen_name="u", user_img="",
        url="", media=[], tickers=tickers, hashtags=[], title="",
        media_types=[], created_at=_now() - timedelta(hours=hours_ago),
        sentiment_label=label, sentiment_score=score,
        assets=[{"symbol": t, "kind": kind,
                 "financials": {"change_percent": change_pct}} for t in tickers],
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

    assert btc["mentions_24h"] == 2
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

    # 7 tweets today, 1 tweet each in days 1-6 (baseline = 7/7 = 1, multiplier = 7)
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
        _tweet(1, ["ETH"], "BULL", 0.7, 2),   # current 24h
        _tweet(2, ["ETH"], "BEAR", -0.5, 30),  # prev 24-48h
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
        _tweet(1, ["OLD"], "BULL", 0.5, 0.5),     # today
        _tweet(2, ["OLD"], "BULL", 0.5, 24 * 10),  # 10 days ago (global history)
    ])

    rows = await get_hidden_gems(Session)
    gem = next((r for r in rows if r["ticker"] == "OLD"), None)
    assert gem is not None
    assert gem["gem_subtype"] == "resurfacing"
    assert gem["days_since_last"] is not None and gem["days_since_last"] >= 9
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_mention_aggregator.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.mention_aggregator'`

- [ ] **Step 3: Implement the aggregator service**

Create `app/services/mention_aggregator.py`:

```python
"""On-demand SQL aggregation over the tweets table using SQLite json_each()."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _score_to_label(score: float | None) -> str:
    if score is None:
        return "NEUTRAL"
    if score > 0.1:
        return "BULL"
    if score < -0.1:
        return "BEAR"
    return "NEUTRAL"


_KIND_FILTER = {
    "CRYPTO": "AND MAX(json_extract(t.assets, '$[0].kind')) = 'CRYPTO'",
    "EQUITY": "AND MAX(json_extract(t.assets, '$[0].kind')) = 'EQUITY'",
    "FOREX":  "AND MAX(json_extract(t.assets, '$[0].kind')) = 'FOREX'",
}


async def get_mention_heat(
    Session: async_sessionmaker,
    asset_kind: str = "all",
    min_mentions: int = 50,
) -> list[dict]:
    now = _now()
    cutoff_7d  = now - timedelta(days=7)
    cutoff_24h = now - timedelta(hours=24)
    kind_clause = _KIND_FILTER.get(asset_kind.upper(), "")

    sql = text(f"""
        SELECT
            j.value AS ticker,
            CAST(SUM(CASE WHEN t.created_at >= :c24 THEN 1 ELSE 0 END) AS INTEGER) AS mentions_24h,
            AVG(CASE WHEN t.created_at >= :c24 THEN t.sentiment_score ELSE NULL END) AS avg_sentiment_24h,
            MAX(json_extract(t.assets, '$[0].kind')) AS asset_kind,
            AVG(CASE WHEN t.created_at >= :c24
                     THEN json_extract(t.assets, '$[0].financials.change_percent')
                     ELSE NULL END) AS price_direction
        FROM tweets t, json_each(t.tickers) j
        WHERE t.created_at >= :c7d
          AND t.tickers IS NOT NULL AND t.tickers != '[]'
        GROUP BY j.value
        HAVING SUM(CASE WHEN t.created_at >= :c24 THEN 1 ELSE 0 END) >= :min_m
        {kind_clause}
        ORDER BY mentions_24h DESC
        LIMIT 100
    """)

    async with Session() as s:
        result = await s.execute(sql, {"c7d": cutoff_7d, "c24": cutoff_24h, "min_m": min_mentions})
        rows = result.mappings().all()

    return [
        {
            "ticker": r["ticker"],
            "mentions_24h": r["mentions_24h"],
            "avg_sentiment_24h": r["avg_sentiment_24h"] or 0.0,
            "sentiment_label_24h": _score_to_label(r["avg_sentiment_24h"]),
            "asset_kind": r["asset_kind"] or "EQUITY",
            "price_direction": r["price_direction"],
        }
        for r in rows
    ]


async def get_sentiment_shift(
    Session: async_sessionmaker,
    asset_kind: str = "all",
) -> list[dict]:
    now = _now()
    cutoff_7d  = now - timedelta(days=7)
    cutoff_48h = now - timedelta(hours=48)
    cutoff_24h = now - timedelta(hours=24)
    kind_clause = _KIND_FILTER.get(asset_kind.upper(), "")

    sql = text(f"""
        SELECT
            j.value AS ticker,
            CAST(SUM(CASE WHEN t.created_at >= :c24 THEN 1 ELSE 0 END) AS INTEGER) AS mentions_24h,
            AVG(CASE WHEN t.created_at >= :c24 THEN t.sentiment_score ELSE NULL END) AS avg_24h,
            AVG(CASE WHEN t.created_at >= :c48 AND t.created_at < :c24
                     THEN t.sentiment_score ELSE NULL END) AS avg_prev,
            MAX(json_extract(t.assets, '$[0].kind')) AS asset_kind
        FROM tweets t, json_each(t.tickers) j
        WHERE t.created_at >= :c7d
          AND t.tickers IS NOT NULL AND t.tickers != '[]'
        GROUP BY j.value
        HAVING SUM(CASE WHEN t.created_at >= :c24 THEN 1 ELSE 0 END) > 0
          AND AVG(CASE WHEN t.created_at >= :c48 AND t.created_at < :c24
                       THEN t.sentiment_score ELSE NULL END) IS NOT NULL
        {kind_clause}
    """)

    async with Session() as s:
        result = await s.execute(sql, {"c7d": cutoff_7d, "c48": cutoff_48h, "c24": cutoff_24h})
        rows = result.mappings().all()

    _score = {"BULL": 1, "NEUTRAL": 0, "BEAR": -1}

    def swing(label_now: str, label_prev: str) -> int:
        return abs(_score.get(label_now, 0) - _score.get(label_prev, 0))

    items = []
    for r in rows:
        label_24h = _score_to_label(r["avg_24h"])
        label_prev = _score_to_label(r["avg_prev"])
        if swing(label_24h, label_prev) == 0:
            continue
        items.append({
            "ticker": r["ticker"],
            "mentions_24h": r["mentions_24h"],
            "avg_sentiment_24h": r["avg_24h"] or 0.0,
            "sentiment_label_24h": label_24h,
            "sentiment_label_prev": label_prev,
            "asset_kind": r["asset_kind"] or "EQUITY",
        })

    items.sort(key=lambda x: swing(x["sentiment_label_24h"], x["sentiment_label_prev"]), reverse=True)
    return items[:10]


async def get_volume_baseline(
    Session: async_sessionmaker,
    asset_kind: str = "all",
    threshold: float = 1.5,
) -> list[dict]:
    now = _now()
    cutoff_7d  = now - timedelta(days=7)
    cutoff_24h = now - timedelta(hours=24)
    kind_clause = _KIND_FILTER.get(asset_kind.upper(), "")

    sql = text(f"""
        SELECT
            j.value AS ticker,
            CAST(SUM(CASE WHEN t.created_at >= :c24 THEN 1 ELSE 0 END) AS INTEGER) AS mentions_24h,
            COUNT(*) / 7.0 AS baseline_7d_avg,
            CASE WHEN COUNT(*) > 0
                 THEN SUM(CASE WHEN t.created_at >= :c24 THEN 1.0 ELSE 0 END) / (COUNT(*) / 7.0)
                 ELSE NULL END AS volume_multiplier,
            MAX(json_extract(t.assets, '$[0].kind')) AS asset_kind
        FROM tweets t, json_each(t.tickers) j
        WHERE t.created_at >= :c7d
          AND t.tickers IS NOT NULL AND t.tickers != '[]'
        GROUP BY j.value
        HAVING SUM(CASE WHEN t.created_at >= :c24 THEN 1 ELSE 0 END) > 5
          AND (COUNT(*) / 7.0) > 0
          AND SUM(CASE WHEN t.created_at >= :c24 THEN 1.0 ELSE 0 END) / (COUNT(*) / 7.0) > :thr
        {kind_clause}
        ORDER BY volume_multiplier DESC
        LIMIT 10
    """)

    async with Session() as s:
        result = await s.execute(sql, {"c7d": cutoff_7d, "c24": cutoff_24h, "thr": threshold})
        rows = result.mappings().all()

    return [
        {
            "ticker": r["ticker"],
            "mentions_24h": r["mentions_24h"],
            "baseline_7d_avg": r["baseline_7d_avg"],
            "volume_multiplier": r["volume_multiplier"],
            "asset_kind": r["asset_kind"] or "EQUITY",
        }
        for r in rows
    ]


async def get_hidden_gems(
    Session: async_sessionmaker,
    asset_kind: str = "all",
) -> list[dict]:
    now = _now()
    cutoff_7d  = now - timedelta(days=7)
    cutoff_24h = now - timedelta(hours=24)
    kind_clause = _KIND_FILTER.get(asset_kind.upper(), "")

    # Two-part query:
    # active: tickers with mentions in last 24h
    # history: global first_seen and last_seen_before_24h from entire tweets table
    sql = text(f"""
        WITH active AS (
            SELECT
                j.value AS ticker,
                CAST(COUNT(*) AS INTEGER) AS mentions_24h,
                MAX(json_extract(t.assets, '$[0].kind')) AS asset_kind
            FROM tweets t, json_each(t.tickers) j
            WHERE t.created_at >= :c24
              AND t.tickers IS NOT NULL AND t.tickers != '[]'
            GROUP BY j.value
            {kind_clause}
        ),
        history AS (
            SELECT
                j.value AS ticker,
                MIN(t.created_at) AS first_seen,
                MAX(CASE WHEN t.created_at < :c24 THEN t.created_at ELSE NULL END)
                    AS last_seen_before_window
            FROM tweets t, json_each(t.tickers) j
            WHERE t.tickers IS NOT NULL AND t.tickers != '[]'
            GROUP BY j.value
        )
        SELECT
            a.ticker,
            a.mentions_24h,
            a.asset_kind,
            h.first_seen,
            h.last_seen_before_window,
            CASE
                WHEN h.first_seen >= :c24 THEN 'new'
                WHEN h.last_seen_before_window IS NULL OR h.last_seen_before_window < :c7d
                     THEN 'resurfacing'
                ELSE NULL
            END AS gem_subtype,
            CASE
                WHEN h.last_seen_before_window IS NOT NULL
                THEN CAST(
                    (julianday('now') - julianday(h.last_seen_before_window))
                    AS INTEGER)
                ELSE NULL
            END AS days_since_last
        FROM active a
        JOIN history h ON a.ticker = h.ticker
        WHERE gem_subtype IS NOT NULL
        ORDER BY a.mentions_24h DESC
        LIMIT 20
    """)

    async with Session() as s:
        result = await s.execute(sql, {"c24": cutoff_24h, "c7d": cutoff_7d})
        rows = result.mappings().all()

    return [
        {
            "ticker": r["ticker"],
            "mentions_24h": r["mentions_24h"],
            "asset_kind": r["asset_kind"] or "EQUITY",
            "gem_subtype": r["gem_subtype"],
            "days_since_last": r["days_since_last"],
            "first_seen": str(r["first_seen"]) if r["first_seen"] else None,
            "last_seen": str(r["last_seen_before_window"]) if r["last_seen_before_window"] else None,
        }
        for r in rows
    ]
```

- [ ] **Step 4: Run tests — all should pass**

```bash
pytest tests/test_mention_aggregator.py -v
```

Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/services/mention_aggregator.py tests/test_mention_aggregator.py
git commit -m "feat: add SQL-based mention aggregator using json_each"
```

---

## Task 2: Overview API Router (including macro strip)

**Files:**
- Create: `app/api/overview.py`
- Create: `tests/test_overview_api.py`

The macro strip reuses the same `get_tradingview_quote` + TTL-cache pattern from `macro_market.py`. All other endpoints call the aggregator functions and pass the `Session` factory directly from `main`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_overview_api.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch("app.api.main.run_stream", new_callable=AsyncMock):
        from app.api.main import app
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def test_mention_heat_returns_list(client):
    resp = client.get("/api/overview/mention-heat")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_mention_heat_min_mentions_param(client):
    resp = client.get("/api/overview/mention-heat?min_mentions=200")
    assert resp.status_code == 200


def test_sentiment_shift_returns_list(client):
    resp = client.get("/api/overview/sentiment-shift")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_volume_baseline_returns_list(client):
    resp = client.get("/api/overview/volume-baseline")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_hidden_gems_returns_list(client):
    resp = client.get("/api/overview/hidden-gems")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_macro_strip_returns_list(client):
    mock_quote = {"price": 5000.0, "change_percent": 0.5}
    with patch("app.api.overview.get_tradingview_quote",
               new_callable=AsyncMock, return_value=mock_quote):
        resp = client.get("/api/overview/macro-strip")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if data:
        assert "label" in data[0]
        assert "price" in data[0]
        assert "change_pct" in data[0]
        assert "sparkline" in data[0]
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_overview_api.py -v
```

Expected: import errors or 404s.

- [ ] **Step 3: Create the router**

Create `app/api/overview.py`:

```python
"""Overview API: macro strip + on-demand tweet mention analytics."""

import asyncio
import logging
import time

from fastapi import APIRouter, Query

from ..services.mention_aggregator import (
    get_hidden_gems,
    get_mention_heat,
    get_sentiment_shift,
    get_volume_baseline,
)
from ..services.tradingview_quote import get_tradingview_quote

router = APIRouter(prefix="/api/overview", tags=["overview"])
logger = logging.getLogger(__name__)

# ─── Macro strip ────────────────────────────────────────────────────────────

_STRIP_TICKERS: list[tuple[str, str, str]] = [
    ("SPX",  "TVC:SPX",           "index"),
    ("NDX",  "IG:NASDAQ",         "index"),
    ("BTC",  "BITSTAMP:BTCUSD",   "crypto"),
    ("ETH",  "BITSTAMP:ETHUSD",   "crypto"),
    ("DXY",  "TVC:DXY",           "forex"),
    ("VIX",  "TVC:VIX",           "index"),
    ("GOLD", "TVC:GOLD",          "index"),
]

_STRIP_CACHE_TTL = 300  # seconds
_strip_cache: tuple[float, list[dict]] | None = None
_strip_lock = asyncio.Lock()


async def _build_strip() -> list[dict]:
    sem = asyncio.Semaphore(4)

    async def _fetch(label: str, symbol: str, hint: str) -> dict | None:
        async with sem:
            try:
                result = await get_tradingview_quote(symbol, asset_hint=hint)
                if not isinstance(result, dict):
                    return None
                price = result.get("price")
                if not isinstance(price, (int, float)):
                    return None
                return {
                    "label": label,
                    "symbol": symbol,
                    "price": float(price),
                    "change_pct": float(result.get("change_percent") or 0.0),
                    "sparkline": [],   # reserved for future intraday bars
                }
            except Exception as exc:
                logger.debug("[macro-strip] %s failed: %r", symbol, exc)
                return None

    results = await asyncio.gather(*[_fetch(l, s, h) for l, s, h in _STRIP_TICKERS])
    return [r for r in results if r is not None]


async def _get_strip() -> list[dict]:
    global _strip_cache
    async with _strip_lock:
        if _strip_cache is not None:
            ts, payload = _strip_cache
            if time.time() - ts < _STRIP_CACHE_TTL:
                return payload
        payload = await _build_strip()
        _strip_cache = (time.time(), payload)
        return payload


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/macro-strip")
async def macro_strip():
    return await _get_strip()


@router.get("/mention-heat")
async def mention_heat(
    asset_kind: str = Query(default="all"),
    min_mentions: int = Query(default=50, ge=1),
):
    from . import main as _main
    return await get_mention_heat(_main.Session, asset_kind=asset_kind, min_mentions=min_mentions)


@router.get("/sentiment-shift")
async def sentiment_shift(asset_kind: str = Query(default="all")):
    from . import main as _main
    return await get_sentiment_shift(_main.Session, asset_kind=asset_kind)


@router.get("/volume-baseline")
async def volume_baseline(asset_kind: str = Query(default="all")):
    from . import main as _main
    return await get_volume_baseline(_main.Session, asset_kind=asset_kind)


@router.get("/hidden-gems")
async def hidden_gems(asset_kind: str = Query(default="all")):
    from . import main as _main
    return await get_hidden_gems(_main.Session, asset_kind=asset_kind)
```

- [ ] **Step 4: Run tests — all should pass**

```bash
pytest tests/test_overview_api.py -v
```

Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/api/overview.py tests/test_overview_api.py
git commit -m "feat: add /api/overview/* endpoints with macro strip and mention analytics"
```

---

## Task 3: Wire Router into main.py

**Files:**
- Modify: `app/api/main.py`

- [ ] **Step 1: Add two lines**

In `app/api/main.py`, add the import after the existing `from ..services.*` block:

```python
from .overview import router as overview_router
```

After the `app = FastAPI(...)` line, add:

```python
app.include_router(overview_router)
```

No worker or repo to add — the router queries the DB directly via `Session`.

- [ ] **Step 2: Smoke-test**

```bash
uvicorn app.api.main:app --port 7999 --reload
```

Visit `http://localhost:7999/api/overview/mention-heat` → returns `[]`. Visit `/api/overview/macro-strip` → may take a few seconds while TradingView connects, then returns the strip items.

- [ ] **Step 3: Commit**

```bash
git add app/api/main.py
git commit -m "feat: register overview router in FastAPI app"
```

---

## Task 4: TypeScript Types + Install Recharts

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/package.json`

- [ ] **Step 1: Install recharts**

```bash
cd frontend && npm install recharts
```

- [ ] **Step 2: Append new interfaces to `frontend/src/types.ts`**

```typescript
export type AssetKind = 'all' | 'EQUITY' | 'CRYPTO' | 'FOREX'

export type SentimentLabel = 'BULL' | 'BEAR' | 'NEUTRAL'

export interface MacroTickerItem {
  label: string          // "SPX" | "NDX" | "BTC" | "ETH" | "DXY" | "VIX" | "GOLD"
  symbol: string
  price: number
  change_pct: number
  sparkline: number[]    // [] until intraday bars are added
}

export interface MentionHeatCell {
  ticker: string
  mentions_24h: number
  avg_sentiment_24h: number      // -1 to 1
  sentiment_label_24h: SentimentLabel
  asset_kind: string
  price_direction: number | null
}

export interface SentimentShiftItem {
  ticker: string
  mentions_24h: number
  sentiment_label_24h: SentimentLabel
  sentiment_label_prev: SentimentLabel
  asset_kind: string
}

export interface VolumeBaselineItem {
  ticker: string
  mentions_24h: number
  baseline_7d_avg: number
  volume_multiplier: number
  asset_kind: string
}

export interface HiddenGemItem {
  ticker: string
  mentions_24h: number
  gem_subtype: 'new' | 'resurfacing'
  days_since_last: number | null
  first_seen: string | null
  last_seen: string | null
  asset_kind: string
}
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts frontend/package.json frontend/package-lock.json
git commit -m "feat: add TypeScript overview types and install recharts"
```

---

## Task 5: Frontend Hooks

**Files:**
- Create: `frontend/src/hooks/useMacroStrip.ts`
- Create: `frontend/src/hooks/useMentionHeat.ts`
- Create: `frontend/src/hooks/useSentimentShift.ts`
- Create: `frontend/src/hooks/useVolumeBaseline.ts`
- Create: `frontend/src/hooks/useHiddenGems.ts`

All five follow the exact same pattern as `useBinanceGainersLosers`: `useEffect` + `fetch` + `AbortController`. Re-fetches when `assetKind` changes.

- [ ] **Step 1: Create all five hooks**

`frontend/src/hooks/useMacroStrip.ts`:
```typescript
import { useEffect, useState } from 'react'
import type { MacroTickerItem } from '../types'

export function useMacroStrip() {
  const [data, setData] = useState<MacroTickerItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(false)
    fetch('/api/overview/macro-strip', { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error('macro-strip'); return r.json() })
      .then(p => setData(Array.isArray(p) ? p : []))
      .catch(e => { if (e.name !== 'AbortError') setError(true) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [])

  return { data, loading, error }
}
```

`frontend/src/hooks/useMentionHeat.ts`:
```typescript
import { useEffect, useState } from 'react'
import type { AssetKind, MentionHeatCell } from '../types'

export function useMentionHeat(assetKind: AssetKind = 'all', minMentions = 50) {
  const [data, setData] = useState<MentionHeatCell[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(false)
    const params = new URLSearchParams({ asset_kind: assetKind, min_mentions: String(minMentions) })
    fetch(`/api/overview/mention-heat?${params}`, { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error('mention-heat'); return r.json() })
      .then(p => setData(Array.isArray(p) ? p : []))
      .catch(e => { if (e.name !== 'AbortError') setError(true) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [assetKind, minMentions])

  return { data, loading, error }
}
```

`frontend/src/hooks/useSentimentShift.ts`:
```typescript
import { useEffect, useState } from 'react'
import type { AssetKind, SentimentShiftItem } from '../types'

export function useSentimentShift(assetKind: AssetKind = 'all') {
  const [data, setData] = useState<SentimentShiftItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(false)
    const params = new URLSearchParams({ asset_kind: assetKind })
    fetch(`/api/overview/sentiment-shift?${params}`, { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error('sentiment-shift'); return r.json() })
      .then(p => setData(Array.isArray(p) ? p : []))
      .catch(e => { if (e.name !== 'AbortError') setError(true) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [assetKind])

  return { data, loading, error }
}
```

`frontend/src/hooks/useVolumeBaseline.ts`:
```typescript
import { useEffect, useState } from 'react'
import type { AssetKind, VolumeBaselineItem } from '../types'

export function useVolumeBaseline(assetKind: AssetKind = 'all') {
  const [data, setData] = useState<VolumeBaselineItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(false)
    const params = new URLSearchParams({ asset_kind: assetKind })
    fetch(`/api/overview/volume-baseline?${params}`, { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error('volume-baseline'); return r.json() })
      .then(p => setData(Array.isArray(p) ? p : []))
      .catch(e => { if (e.name !== 'AbortError') setError(true) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [assetKind])

  return { data, loading, error }
}
```

`frontend/src/hooks/useHiddenGems.ts`:
```typescript
import { useEffect, useState } from 'react'
import type { AssetKind, HiddenGemItem } from '../types'

export function useHiddenGems(assetKind: AssetKind = 'all') {
  const [data, setData] = useState<HiddenGemItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(false)
    const params = new URLSearchParams({ asset_kind: assetKind })
    fetch(`/api/overview/hidden-gems?${params}`, { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error('hidden-gems'); return r.json() })
      .then(p => setData(Array.isArray(p) ? p : []))
      .catch(e => { if (e.name !== 'AbortError') setError(true) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [assetKind])

  return { data, loading, error }
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat: add five overview data hooks"
```

---

## Task 6: MacroStrip Component

**Files:**
- Create: `frontend/src/components/MacroStrip.tsx`

Renders a dark horizontal strip. Sparkline renders only when `data.length >= 2` — it's empty `[]` from the API right now, so the slot is invisible but the layout is forward-compatible.

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/MacroStrip.tsx
import { useMacroStrip } from '../hooks/useMacroStrip'
import type { MacroTickerItem } from '../types'

function Sparkline({ data, up }: { data: number[]; up: boolean }) {
  if (data.length < 2) return null
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const W = 56, H = 20
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * W
    const y = H - ((v - min) / range) * (H - 2) - 1
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return (
    <svg width={W} height={H} className="shrink-0">
      <polyline points={pts} fill="none"
        stroke={up ? '#34d399' : '#f87171'} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  )
}

function MacroTicker({ item }: { item: MacroTickerItem }) {
  const up = item.change_pct >= 0
  return (
    <div className="flex items-center gap-2 px-4 py-2 shrink-0">
      <span className="text-xs font-semibold text-zinc-300 w-10 shrink-0">{item.label}</span>
      <Sparkline data={item.sparkline} up={up} />
      <div className="flex flex-col items-end min-w-[72px]">
        <span className="text-xs font-mono text-zinc-100 leading-tight">
          {item.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
        </span>
        <span className={`text-[11px] font-mono leading-tight ${up ? 'text-emerald-400' : 'text-rose-400'}`}>
          {up ? '+' : ''}{item.change_pct.toFixed(2)}%
        </span>
      </div>
    </div>
  )
}

export default function MacroStrip() {
  const { data, loading } = useMacroStrip()
  return (
    <div className="w-full bg-zinc-950 border-b border-zinc-800 overflow-x-auto">
      <div className="flex items-center divide-x divide-zinc-800">
        {loading && (
          <span className="px-4 py-2 text-xs text-zinc-500 animate-pulse">Loading…</span>
        )}
        {data.map(item => <MacroTicker key={item.label} item={item} />)}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/MacroStrip.tsx
git commit -m "feat: MacroStrip component with price and delta"
```

---

## Task 7: AssetFilterTabs Component

**Files:**
- Create: `frontend/src/components/AssetFilterTabs.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/AssetFilterTabs.tsx
import type { AssetKind } from '../types'

const TABS: Array<{ label: string; value: AssetKind }> = [
  { label: 'All',    value: 'all'    },
  { label: 'Stocks', value: 'EQUITY' },
  { label: 'Crypto', value: 'CRYPTO' },
  { label: 'Forex',  value: 'FOREX'  },
]

function timeAgo(iso: string | null): string {
  if (!iso) return ''
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  return `${Math.round(mins / 60)}h ago`
}

interface Props {
  active: AssetKind
  onChange: (kind: AssetKind) => void
  updatedAt?: string | null
}

export default function AssetFilterTabs({ active, onChange, updatedAt }: Props) {
  return (
    <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800 bg-zinc-900">
      <div className="flex gap-1">
        {TABS.map(tab => (
          <button
            key={tab.value}
            onClick={() => onChange(tab.value)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              active === tab.value
                ? 'bg-zinc-100 text-zinc-900'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {updatedAt && (
        <span className="text-[11px] text-zinc-500">Updated {timeAgo(updatedAt)}</span>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/AssetFilterTabs.tsx
git commit -m "feat: AssetFilterTabs with freshness timestamp"
```

---

## Task 8: MentionHeatmap Component

**Files:**
- Create: `frontend/src/components/MentionHeatmap.tsx`

Uses Recharts `Treemap` with a custom SVG `content` renderer. Cell fill = sentiment, cell stroke = price direction.

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/MentionHeatmap.tsx
import { Treemap, ResponsiveContainer } from 'recharts'
import type { AssetKind, MentionHeatCell } from '../types'
import { useMentionHeat } from '../hooks/useMentionHeat'

function sentimentFill(avg: number): string {
  if (avg >= 0.35) return '#059669'   // emerald-600
  if (avg >= 0.1)  return '#10b981'   // emerald-500
  if (avg >= -0.1) return '#3f3f46'   // zinc-700
  if (avg >= -0.35) return '#d97706'  // amber-600
  return '#e11d48'                    // rose-600
}

function priceBorder(dir: number | null): string {
  if (dir === null) return '#52525b'
  return dir > 0 ? '#22c55e' : '#ef4444'
}

interface CellProps {
  x?: number; y?: number; width?: number; height?: number
  name?: string; avg_sentiment_24h?: number; price_direction?: number | null
}

function CustomCell({ x = 0, y = 0, width = 0, height = 0,
                       name = '', avg_sentiment_24h = 0, price_direction = null }: CellProps) {
  if (width < 24 || height < 18) return null
  const fontSize = width > 90 ? 13 : width > 50 ? 11 : 9
  return (
    <g>
      <rect x={x + 2} y={y + 2} width={width - 4} height={height - 4}
            fill={sentimentFill(avg_sentiment_24h)}
            stroke={priceBorder(price_direction)} strokeWidth={2} rx={3} />
      {width > 30 && height > 20 && (
        <text x={x + width / 2} y={y + height / 2}
              textAnchor="middle" dominantBaseline="central"
              fill="#f4f4f5" fontSize={fontSize} fontWeight={600}>
          {name}
        </text>
      )}
    </g>
  )
}

interface Props {
  assetKind: AssetKind
  minMentions?: number
  onTickerClick?: (ticker: string) => void
}

export default function MentionHeatmap({ assetKind, minMentions = 50, onTickerClick }: Props) {
  const { data, loading, error } = useMentionHeat(assetKind, minMentions)

  if (loading) return (
    <div className="w-full h-48 bg-zinc-900 rounded-2xl flex items-center justify-center">
      <span className="text-zinc-500 text-sm animate-pulse">Building mention heat…</span>
    </div>
  )

  if (error || data.length === 0) return (
    <div className="w-full h-48 bg-zinc-900 rounded-2xl flex items-center justify-center">
      <span className="text-zinc-500 text-sm text-center px-4">
        {error
          ? 'Could not load mention data.'
          : `No tickers with ${minMentions}+ mentions in the last 24 h.`}
      </span>
    </div>
  )

  const treeData = data.map((c: MentionHeatCell) => ({
    name: c.ticker,
    value: c.mentions_24h,
    avg_sentiment_24h: c.avg_sentiment_24h,
    price_direction: c.price_direction,
  }))

  return (
    <div
      className="w-full h-48 bg-zinc-900 rounded-2xl overflow-hidden cursor-pointer"
      onClick={e => {
        const el = e.target as SVGElement
        const name = el.tagName === 'text' ? el.textContent : null
        if (name && onTickerClick) onTickerClick(name)
      }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <Treemap data={treeData} dataKey="value" aspectRatio={4} content={<CustomCell />} />
      </ResponsiveContainer>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/MentionHeatmap.tsx
git commit -m "feat: MentionHeatmap treemap with sentiment color + price-direction border"
```

---

## Task 9: SentimentShiftWidget

**Files:**
- Create: `frontend/src/components/SentimentShiftWidget.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/SentimentShiftWidget.tsx
import type { AssetKind, SentimentLabel, SentimentShiftItem } from '../types'
import { useSentimentShift } from '../hooks/useSentimentShift'

const BADGE: Record<SentimentLabel, string> = {
  BULL: 'text-emerald-400 bg-emerald-950',
  BEAR: 'text-rose-400 bg-rose-950',
  NEUTRAL: 'text-zinc-400 bg-zinc-800',
}
const DISPLAY: Record<SentimentLabel, string> = { BULL: 'bull', BEAR: 'bear', NEUTRAL: 'neut' }

function Badge({ label }: { label: SentimentLabel }) {
  return (
    <span className={`px-1.5 py-0.5 rounded text-[11px] font-semibold ${BADGE[label]}`}>
      {DISPLAY[label]}
    </span>
  )
}

export default function SentimentShiftWidget({ assetKind }: { assetKind: AssetKind }) {
  const { data, loading, error } = useSentimentShift(assetKind)

  return (
    <div className="bg-zinc-900 rounded-2xl p-4 border border-zinc-800 flex flex-col gap-3">
      <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
        Sentiment Shift
      </h3>
      {loading && <div className="space-y-2">{Array.from({length: 5}).map((_,i) =>
        <div key={i} className="h-6 bg-zinc-800 rounded animate-pulse" />)}</div>}
      {error && <p className="text-xs text-zinc-500">Could not load sentiment shift.</p>}
      {!loading && !error && data.length === 0 &&
        <p className="text-xs text-zinc-500">No sentiment shifts in the last 24 h.</p>}
      {!loading && !error && data.length > 0 && (
        <ol className="space-y-2">
          {data.map((item: SentimentShiftItem) => (
            <li key={item.ticker} className="flex items-center justify-between gap-2">
              <span className="text-xs font-mono text-zinc-100 w-16 shrink-0">{item.ticker}</span>
              <div className="flex items-center gap-1.5 shrink-0">
                <Badge label={item.sentiment_label_prev} />
                <span className="text-zinc-600 text-xs">→</span>
                <Badge label={item.sentiment_label_24h} />
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/SentimentShiftWidget.tsx
git commit -m "feat: SentimentShiftWidget leaderboard"
```

---

## Task 10: VolumeBaselineWidget

**Files:**
- Create: `frontend/src/components/VolumeBaselineWidget.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/VolumeBaselineWidget.tsx
import type { AssetKind, VolumeBaselineItem } from '../types'
import { useVolumeBaseline } from '../hooks/useVolumeBaseline'

export default function VolumeBaselineWidget({ assetKind }: { assetKind: AssetKind }) {
  const { data, loading, error } = useVolumeBaseline(assetKind)
  const maxMult = data.length > 0 ? Math.max(...data.map(d => d.volume_multiplier)) : 1

  return (
    <div className="bg-zinc-900 rounded-2xl p-4 border border-zinc-800 flex flex-col gap-3">
      <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Volume Spike</h3>
      {loading && <div className="space-y-2">{Array.from({length: 5}).map((_,i) =>
        <div key={i} className="h-6 bg-zinc-800 rounded animate-pulse" />)}</div>}
      {error && <p className="text-xs text-zinc-500">Could not load volume data.</p>}
      {!loading && !error && data.length === 0 &&
        <p className="text-xs text-zinc-500">No unusual volume in the last 24 h.</p>}
      {!loading && !error && data.length > 0 && (
        <ol className="space-y-2">
          {data.map((item: VolumeBaselineItem) => (
            <li key={item.ticker} className="flex items-center gap-2">
              <span className="text-xs font-mono text-zinc-100 w-16 shrink-0">{item.ticker}</span>
              <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                <div className="h-full bg-amber-500 rounded-full"
                     style={{ width: `${Math.min((item.volume_multiplier / maxMult) * 100, 100)}%` }} />
              </div>
              <span className="text-[11px] font-mono text-amber-400 w-14 text-right shrink-0">
                +{item.volume_multiplier.toFixed(1)}×
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/VolumeBaselineWidget.tsx
git commit -m "feat: VolumeBaselineWidget amber bar leaderboard"
```

---

## Task 11: HiddenGemWidget

**Files:**
- Create: `frontend/src/components/HiddenGemWidget.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/HiddenGemWidget.tsx
import type { AssetKind, HiddenGemItem } from '../types'
import { useHiddenGems } from '../hooks/useHiddenGems'

function GemBadge({ subtype }: { subtype: 'new' | 'resurfacing' }) {
  return subtype === 'new'
    ? <span className="px-1.5 py-0.5 rounded text-[11px] font-semibold text-violet-300 bg-violet-950">✦ new</span>
    : <span className="px-1.5 py-0.5 rounded text-[11px] font-semibold text-sky-300 bg-sky-950">↩ resurface</span>
}

export default function HiddenGemWidget({ assetKind }: { assetKind: AssetKind }) {
  const { data, loading, error } = useHiddenGems(assetKind)

  return (
    <div className="bg-zinc-900 rounded-2xl p-4 border border-zinc-800 flex flex-col gap-3">
      <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Hidden Gem</h3>
      {loading && <div className="space-y-2">{Array.from({length: 4}).map((_,i) =>
        <div key={i} className="h-6 bg-zinc-800 rounded animate-pulse" />)}</div>}
      {error && <p className="text-xs text-zinc-500">Could not load hidden gems.</p>}
      {!loading && !error && data.length === 0 &&
        <p className="text-xs text-zinc-500">No new or resurfacing tickers yet.</p>}
      {!loading && !error && data.length > 0 && (
        <ol className="space-y-2">
          {data.slice(0, 10).map((item: HiddenGemItem) => (
            <li key={item.ticker} className="flex items-center justify-between gap-2">
              <span className="text-xs font-mono text-zinc-100 w-16 shrink-0">{item.ticker}</span>
              <GemBadge subtype={item.gem_subtype} />
              <span className="text-[11px] text-zinc-500 ml-auto shrink-0">
                {item.gem_subtype === 'resurfacing' && item.days_since_last != null
                  ? `${item.days_since_last}d ago`
                  : 'first time'}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/HiddenGemWidget.tsx
git commit -m "feat: HiddenGemWidget with new/resurfacing badges"
```

---

## Task 12: OverviewDashboard

**Files:**
- Create: `frontend/src/components/OverviewDashboard.tsx`

- [ ] **Step 1: Create the assembly component**

```tsx
// frontend/src/components/OverviewDashboard.tsx
import { useState } from 'react'
import type { AssetKind } from '../types'
import AssetFilterTabs from './AssetFilterTabs'
import HiddenGemWidget from './HiddenGemWidget'
import MacroStrip from './MacroStrip'
import MentionHeatmap from './MentionHeatmap'
import SentimentShiftWidget from './SentimentShiftWidget'
import VolumeBaselineWidget from './VolumeBaselineWidget'

interface Props {
  onTickerClick?: (ticker: string) => void
}

export default function OverviewDashboard({ onTickerClick }: Props) {
  const [assetKind, setAssetKind] = useState<AssetKind>('all')

  return (
    <div className="flex flex-col">
      <MacroStrip />
      <AssetFilterTabs active={assetKind} onChange={setAssetKind} />

      <div className="p-4 flex flex-col gap-4">
        <section>
          <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-2">
            Mention Heat · 24 h
          </h2>
          <MentionHeatmap
            assetKind={assetKind}
            minMentions={50}
            onTickerClick={onTickerClick}
          />
        </section>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <SentimentShiftWidget assetKind={assetKind} />
          <VolumeBaselineWidget assetKind={assetKind} />
          <HiddenGemWidget assetKind={assetKind} />
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/OverviewDashboard.tsx
git commit -m "feat: OverviewDashboard assembly"
```

---

## Task 13: Wire OverviewDashboard into App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add import**

At the top of `frontend/src/App.tsx`:

```tsx
import OverviewDashboard from './components/OverviewDashboard'
```

- [ ] **Step 2: Replace the home-route widget block**

Find the block in the JSX that renders for `route === 'home'` (currently `FearGreedWidget`, `RedditWsbWidget`, `MarketOverview`). Replace the widget section with:

```tsx
{route === 'home' && (
  <OverviewDashboard onTickerClick={(ticker) => setTickerFilter(ticker)} />
)}
```

`FearGreedWidget`, `RedditWsbWidget`, and `MarketOverview` are replaced in the main content area only. Remove those three component calls from the home route block but keep their imports if they're used on other routes — otherwise remove unused imports too.

- [ ] **Step 3: Verify in browser**

```bash
# Terminal 1
uvicorn app.api.main:app --port 7999 --reload

# Terminal 2
cd frontend && npm run dev
```

Open `http://localhost:5173`. Confirm:
- Macro strip renders across the full width with price + Δ% for each benchmark
- Filter tabs (All / Stocks / Crypto / Forex) visible
- Treemap shows cells (or empty-state if no tweet data)
- Clicking a filter re-fetches all three widgets
- Clicking a treemap cell sets the ticker filter in the sidebar

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: replace home route with OverviewDashboard"
```

---

## Self-Review

| Brief requirement | Covered |
|---|---|
| Macro strip: 7 benchmarks + price + Δ% | Task 2 (TVC quotes) + Task 6 (UI) |
| Sparklines (reserved, `[]` now) | Task 6 renders nothing when `[]` — forward-compatible |
| Asset filter tabs All/Stocks/Crypto/Forex | Task 7 |
| Mention Heat treemap: size=mentions, fill=sentiment, border=price dir | Tasks 1+8 |
| Click treemap cell → ticker filter | Tasks 8+13 |
| Treemap empty-state nudge | Task 8 |
| Sentiment Shift top 10 by swing magnitude | Tasks 1+9 |
| was→now label badges (bull/bear/neut) | Task 9 |
| Volume Baseline amber bar + multiplier | Tasks 1+10 |
| Hidden Gem: new ✦ + resurfacing ↩ | Tasks 1+11 |
| days-since-last for resurfacing | Task 1 (SQL julianday) + Task 11 |
| Design tokens: zinc-900, emerald/rose/amber | All component tasks |
| No pre-computed table or worker | Removed — on-demand SQL ✓ |
| Reuse TradingView quote pattern for macro | Task 2 uses same `get_tradingview_quote` ✓ |
