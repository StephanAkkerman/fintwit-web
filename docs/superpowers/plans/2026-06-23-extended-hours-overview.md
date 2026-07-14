# Extended Hours Overview Panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a contextual `ExtendedHoursPanel` to the `/stocks` page that shows US equity futures, ETF extended-hours prices, and tweet-mention stats for the active pre-market or after-hours window.

**Architecture:** A new `GET /api/stocks/extended-hours` endpoint assembles the snapshot from three sources — TradingView futures prices, Yahoo ETF extended-hours prices, and a new SQL aggregation of tweets in the session window — caches the result server-side for 3 minutes, and returns it as one JSON payload. A polling React hook drives the panel, which returns `null` during regular hours and renders a compact digest otherwise. The "closed" (overnight/weekend) state shows a collapsed chip that expands to the last completed session's data.

**Tech Stack:** FastAPI, SQLAlchemy async, `ticker-price-data` package (`get_tradingview_quote`, `get_stock_info`, `get_us_stock_session`), React 18 + TypeScript strict, Vitest, `@testing-library/react`

## Global Constraints

- Python 3.10–3.13 — use `zoneinfo.ZoneInfo`, not `pytz`
- Ruff + Black, line length 88
- Datetimes in SQLite are naive UTC — strip `tzinfo` before binding to SQL
- Do not reimplement price logic; use `ticker_price_data` package imports only
- TypeScript strict mode — no `any`
- Tailwind dark-mode-first: amber tokens for pre-market, violet tokens for after-hours (matches `StockMarketHoursBanner`)

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `app/services/mention_aggregator.py` | Add `get_extended_hours_stats` |
| Create | `app/services/extended_hours_service.py` | Window logic, price fetching, cache, snapshot assembly |
| Modify | `app/api/main.py` | Add `GET /api/stocks/extended-hours` |
| Modify | `tests/test_mention_aggregator.py` | Tests for `get_extended_hours_stats` |
| Create | `tests/test_extended_hours_service.py` | Tests for window bounds + snapshot shape |
| Create | `tests/test_extended_hours_api.py` | API endpoint tests |
| Modify | `frontend/src/types.ts` | Add 4 new types |
| Create | `frontend/src/hooks/useExtendedHours.ts` | Polling hook |
| Create | `frontend/src/components/ExtendedHoursPanel.tsx` | Panel UI |
| Create | `frontend/src/__tests__/ExtendedHoursPanel.test.tsx` | Vitest component tests |
| Modify | `frontend/src/App.tsx` | Insert `<ExtendedHoursPanel />` above `StockMarketHoursBanner` |

---

## Task 1: `get_extended_hours_stats` in `mention_aggregator.py`

**Files:**
- Modify: `app/services/mention_aggregator.py`
- Modify: `tests/test_mention_aggregator.py`

**Interfaces:**
- Produces: `get_extended_hours_stats(Session, since_dt: datetime, until_dt: datetime, top_n: int = 10) -> dict`
  - `since_dt` / `until_dt` are naive UTC datetimes
  - Returns `{ "total_mentions": int, "top_tickers": [{"ticker": str, "mentions": int, "sentiment": "BULL"|"BEAR"|"NEUTRAL"}], "sentiment_distribution": {"BULL": int, "BEAR": int, "NEUTRAL": int} }`

- [ ] **Step 1: Add failing tests to `tests/test_mention_aggregator.py`**

Append after the last existing test:

```python
async def test_extended_hours_stats_counts(Session):
    from app.services.mention_aggregator import get_extended_hours_stats

    now = _now()
    await _insert(Session, [
        _tweet(10, ["NVDA"], "BULL",  0.8,  1, "EQUITY"),  # in window
        _tweet(11, ["NVDA"], "BULL",  0.9,  1, "EQUITY"),  # in window
        _tweet(12, ["AAPL"], "BEAR", -0.5,  1, "EQUITY"),  # in window
        _tweet(13, ["NVDA"], "BULL",  0.7, 10, "EQUITY"),  # outside window
    ])
    since = now - timedelta(hours=5)
    until = now + timedelta(hours=1)

    result = await get_extended_hours_stats(Session, since, until, top_n=10)

    assert result["total_mentions"] == 3
    assert result["top_tickers"][0]["ticker"] == "NVDA"
    assert result["top_tickers"][0]["mentions"] == 2
    assert result["top_tickers"][0]["sentiment"] == "BULL"
    assert result["sentiment_distribution"]["BULL"] == 2
    assert result["sentiment_distribution"]["BEAR"] == 1
    assert result["sentiment_distribution"]["NEUTRAL"] == 0


async def test_extended_hours_stats_empty_window(Session):
    from app.services.mention_aggregator import get_extended_hours_stats

    now = _now()
    # Window is entirely in the future — no tweets match.
    since = now + timedelta(hours=1)
    until = now + timedelta(hours=6)

    result = await get_extended_hours_stats(Session, since, until)

    assert result["total_mentions"] == 0
    assert result["top_tickers"] == []
    assert result["sentiment_distribution"] == {"BULL": 0, "BEAR": 0, "NEUTRAL": 0}


async def test_extended_hours_stats_top_n(Session):
    from app.services.mention_aggregator import get_extended_hours_stats

    now = _now()
    # Insert 5 distinct tickers, 3 mentions each.
    for i, ticker in enumerate(["A", "B", "C", "D", "E"]):
        for j in range(3):
            await _insert(Session, [_tweet(i * 10 + j, [ticker], "NEUTRAL", 0.0, 1)])

    since = now - timedelta(hours=5)
    until = now + timedelta(hours=1)

    result = await get_extended_hours_stats(Session, since, until, top_n=3)

    assert len(result["top_tickers"]) == 3
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/test_mention_aggregator.py::test_extended_hours_stats_counts tests/test_mention_aggregator.py::test_extended_hours_stats_empty_window tests/test_mention_aggregator.py::test_extended_hours_stats_top_n -v
```

Expected: `FAILED` with `ImportError: cannot import name 'get_extended_hours_stats'`

- [ ] **Step 3: Add `get_extended_hours_stats` to `app/services/mention_aggregator.py`**

Insert the following function immediately before the `# ─── Per-tweet mention frequency` comment block (around line 435):

```python
async def get_extended_hours_stats(
    Session: async_sessionmaker,
    since_dt: datetime,
    until_dt: datetime,
    top_n: int = 10,
) -> dict:
    """Aggregate tweet-ticker mentions in a fixed window for the extended-hours panel."""
    sql = text("""
        SELECT
            j.value AS ticker,
            CAST(COUNT(*) AS INTEGER) AS mentions,
            SUM(CASE WHEN t.sentiment_score >  0.1 THEN 1 ELSE 0 END) AS bull_count,
            SUM(CASE WHEN t.sentiment_score < -0.1 THEN 1 ELSE 0 END) AS bear_count
        FROM tweets t, json_each(t.tickers) j
        WHERE t.created_at >= :since_dt
          AND t.created_at <  :until_dt
          AND t.tickers IS NOT NULL AND t.tickers != '[]'
        GROUP BY j.value
        ORDER BY mentions DESC
    """)

    async with Session() as s:
        result = await s.execute(sql, {"since_dt": since_dt, "until_dt": until_dt})
        rows = result.mappings().all()

    total_bull = sum(int(r["bull_count"] or 0) for r in rows)
    total_bear = sum(int(r["bear_count"] or 0) for r in rows)
    total_mentions = sum(int(r["mentions"]) for r in rows)

    top_tickers = []
    for r in rows[:top_n]:
        bull = int(r["bull_count"] or 0)
        bear = int(r["bear_count"] or 0)
        sentiment = "BULL" if bull > bear else ("BEAR" if bear > bull else "NEUTRAL")
        top_tickers.append({
            "ticker": r["ticker"],
            "mentions": int(r["mentions"]),
            "sentiment": sentiment,
        })

    return {
        "total_mentions": total_mentions,
        "top_tickers": top_tickers,
        "sentiment_distribution": {
            "BULL": total_bull,
            "BEAR": total_bear,
            "NEUTRAL": total_mentions - total_bull - total_bear,
        },
    }
```

- [ ] **Step 4: Run to confirm pass**

```
pytest tests/test_mention_aggregator.py::test_extended_hours_stats_counts tests/test_mention_aggregator.py::test_extended_hours_stats_empty_window tests/test_mention_aggregator.py::test_extended_hours_stats_top_n -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add app/services/mention_aggregator.py tests/test_mention_aggregator.py
git commit -m "feat: add get_extended_hours_stats to mention_aggregator"
```

---

## Task 2: `app/services/extended_hours_service.py`

**Files:**
- Create: `app/services/extended_hours_service.py`
- Create: `tests/test_extended_hours_service.py`

**Interfaces:**
- Consumes: `get_extended_hours_stats` (Task 1); `get_us_stock_session`, `get_tradingview_quote`, `get_stock_info` from `ticker_price_data`
- Produces:
  - `_window_bounds(session: str) -> tuple[str, str, datetime, datetime]` — `(window_start_iso, window_end_iso, since_naive_utc, until_naive_utc)`
  - `get_snapshot(Session: async_sessionmaker) -> dict | None`
  - Module-level `_fetch_futures() -> list[dict]` and `_fetch_etfs() -> list[dict]` (patchable in tests)

- [ ] **Step 1: Write failing tests in `tests/test_extended_hours_service.py`**

```python
"""Tests for extended_hours_service window logic and snapshot shape."""
import asyncio
import pytest
from datetime import datetime

pytestmark = pytest.mark.asyncio


def test_window_bounds_pre_market():
    from app.services.extended_hours_service import _window_bounds

    start_iso, end_iso, since_utc, until_utc = _window_bounds("pre-market")

    assert "04:00" in start_iso
    assert "09:30" in end_iso
    assert since_utc.tzinfo is None   # must be naive UTC
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
        return [{"label": "ES", "symbol": "CME_MINI:ES1!", "price": 5800.0, "change_pct": 0.3}]

    async def _fake_etfs():
        return [{"symbol": "SPY", "price": 580.0, "extended_price": 581.5, "extended_change_pct": 0.26}]

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
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/test_extended_hours_service.py -v
```

Expected: `FAILED` with `ModuleNotFoundError: No module named 'app.services.extended_hours_service'`

- [ ] **Step 3: Create `app/services/extended_hours_service.py`**

```python
"""Extended-hours snapshot: window bounds, US equity futures, ETF prices, tweet stats."""

import asyncio
import logging
import time
from datetime import datetime, time as dt_time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import async_sessionmaker
from ticker_price_data import get_stock_info
from ticker_price_data.market_session import get_us_stock_session
from ticker_price_data.tradingview_quote import get_tradingview_quote

from .mention_aggregator import get_extended_hours_stats

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

_FUTURES: list[tuple[str, str]] = [
    ("ES", "CME_MINI:ES1!"),
    ("NQ", "CME_MINI:NQ1!"),
    ("YM", "CBOT_MINI:YM1!"),
]
_ETFS: list[str] = ["SPY", "QQQ", "IWM"]

_CACHE_TTL = 180  # seconds
_snapshot_cache: tuple[float, dict] | None = None
_lock = asyncio.Lock()


def _to_naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _window_bounds(session: str) -> tuple[str, str, datetime, datetime]:
    """Return (window_start_iso, window_end_iso, since_naive_utc, until_naive_utc)."""
    now_et = datetime.now(_ET)
    today = now_et.date()

    if session == "pre-market":
        start = datetime.combine(today, dt_time(4, 0),  tzinfo=_ET)
        end   = datetime.combine(today, dt_time(9, 30), tzinfo=_ET)
    elif session == "after-hours":
        start = datetime.combine(today, dt_time(16, 0), tzinfo=_ET)
        end   = datetime.combine(today, dt_time(20, 0), tzinfo=_ET)
    elif session == "regular":
        # Most-recently completed session before open: today's pre-market.
        start = datetime.combine(today, dt_time(4, 0),  tzinfo=_ET)
        end   = datetime.combine(today, dt_time(9, 30), tzinfo=_ET)
    else:
        # closed (overnight, weekend, holiday)
        # Before 4 PM: last completed after-hours was yesterday's.
        # At or after 4 PM: today's after-hours window (or in progress).
        if now_et.hour < 16:
            yesterday = today - timedelta(days=1)
            start = datetime.combine(yesterday, dt_time(16, 0), tzinfo=_ET)
            end   = datetime.combine(yesterday, dt_time(20, 0), tzinfo=_ET)
        else:
            start = datetime.combine(today, dt_time(16, 0), tzinfo=_ET)
            end   = datetime.combine(today, dt_time(20, 0), tzinfo=_ET)

    return (
        start.isoformat(),
        end.isoformat(),
        _to_naive_utc(start),
        _to_naive_utc(end),
    )


async def _fetch_futures() -> list[dict]:
    sem = asyncio.Semaphore(3)

    async def _one(label: str, symbol: str) -> dict | None:
        async with sem:
            try:
                result = await get_tradingview_quote(symbol, asset_hint="index")
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
                }
            except Exception as exc:
                logger.debug("[extended-hours] futures %s failed: %r", symbol, exc)
                return None

    results = await asyncio.gather(*[_one(lbl, sym) for lbl, sym in _FUTURES])
    return [r for r in results if r is not None]


async def _fetch_etfs() -> list[dict]:
    sem = asyncio.Semaphore(3)

    async def _one(symbol: str) -> dict | None:
        async with sem:
            try:
                result = await get_stock_info(symbol)
                if not isinstance(result, dict):
                    return None
                price = result.get("price")
                if not isinstance(price, (int, float)):
                    return None
                ext_price = result.get("extended_price")
                ext_pct   = result.get("extended_change_percent")
                return {
                    "symbol": symbol,
                    "price": float(price),
                    "extended_price":      float(ext_price) if ext_price is not None else None,
                    "extended_change_pct": float(ext_pct)   if ext_pct   is not None else None,
                }
            except Exception as exc:
                logger.debug("[extended-hours] ETF %s failed: %r", symbol, exc)
                return None

    results = await asyncio.gather(*[_one(s) for s in _ETFS])
    return [r for r in results if r is not None]


async def get_snapshot(Session: async_sessionmaker) -> dict | None:
    global _snapshot_cache

    async with _lock:
        if _snapshot_cache is not None:
            ts, payload = _snapshot_cache
            if time.time() - ts < _CACHE_TTL:
                return payload

        try:
            session = get_us_stock_session()
            window_start_iso, window_end_iso, since_dt, until_dt = _window_bounds(session)

            futures, etfs, tweet_stats = await asyncio.gather(
                _fetch_futures(),
                _fetch_etfs(),
                get_extended_hours_stats(Session, since_dt, until_dt),
            )

            payload = {
                "session": session,
                "window_start": window_start_iso,
                "window_end": window_end_iso,
                "futures": futures,
                "etfs": etfs,
                "tweet_stats": tweet_stats,
            }
            _snapshot_cache = (time.time(), payload)
            return payload
        except Exception as exc:
            logger.warning("[extended-hours] snapshot failed: %r", exc)
            return _snapshot_cache[1] if _snapshot_cache is not None else None
```

- [ ] **Step 4: Run to confirm pass**

```
pytest tests/test_extended_hours_service.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add app/services/extended_hours_service.py tests/test_extended_hours_service.py
git commit -m "feat: add extended_hours_service with window logic, price fetching, and cache"
```

---

## Task 3: `GET /api/stocks/extended-hours` endpoint

**Files:**
- Modify: `app/api/main.py`
- Create: `tests/test_extended_hours_api.py`

**Interfaces:**
- Consumes: `get_snapshot` from Task 2 (imported as `get_extended_hours_snapshot`)
- Produces: `GET /api/stocks/extended-hours` → dict payload or 503

- [ ] **Step 1: Write failing test in `tests/test_extended_hours_api.py`**

```python
"""Tests for GET /api/stocks/extended-hours."""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from app.api.main import app

pytestmark = pytest.mark.asyncio

_MOCK_PAYLOAD = {
    "session": "pre-market",
    "window_start": "2026-06-23T04:00:00-04:00",
    "window_end": "2026-06-23T09:30:00-04:00",
    "futures": [{"label": "ES", "symbol": "CME_MINI:ES1!", "price": 5800.0, "change_pct": 0.31}],
    "etfs": [{"symbol": "SPY", "price": 580.0, "extended_price": 581.5, "extended_change_pct": 0.26}],
    "tweet_stats": {
        "total_mentions": 42,
        "top_tickers": [{"ticker": "NVDA", "mentions": 10, "sentiment": "BULL"}],
        "sentiment_distribution": {"BULL": 20, "BEAR": 10, "NEUTRAL": 12},
    },
}


async def test_extended_hours_returns_snapshot():
    app.state.API_KEY = ""
    with patch(
        "app.api.main.get_extended_hours_snapshot",
        new_callable=AsyncMock,
        return_value=_MOCK_PAYLOAD,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/stocks/extended-hours")

    assert r.status_code == 200
    data = r.json()
    assert data["session"] == "pre-market"
    assert len(data["futures"]) == 1
    assert data["tweet_stats"]["total_mentions"] == 42


async def test_extended_hours_503_when_snapshot_none():
    app.state.API_KEY = ""
    with patch(
        "app.api.main.get_extended_hours_snapshot",
        new_callable=AsyncMock,
        return_value=None,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/stocks/extended-hours")

    assert r.status_code == 503
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/test_extended_hours_api.py -v
```

Expected: `FAILED` with `AttributeError: module 'app.api.main' has no attribute 'get_extended_hours_snapshot'`

- [ ] **Step 3: Add import and endpoint to `app/api/main.py`**

Add the import near the other service imports (around line 41):

```python
from ..services.extended_hours_service import get_snapshot as get_extended_hours_snapshot
```

Add the endpoint after the existing `@app.get("/api/stocks/market-hours")` handler (around line 257):

```python
@app.get("/api/stocks/extended-hours")
async def stocks_extended_hours(_=Depends(api_key_dep)):
    data = await get_extended_hours_snapshot(Session)
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data
```

- [ ] **Step 4: Run to confirm pass**

```
pytest tests/test_extended_hours_api.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Confirm no regressions**

```
pytest --maxfail=1 --disable-warnings -q
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add app/api/main.py tests/test_extended_hours_api.py
git commit -m "feat: add GET /api/stocks/extended-hours endpoint"
```

---

## Task 4: Frontend types in `types.ts`

**Files:**
- Modify: `frontend/src/types.ts`

**Interfaces:**
- Produces: `ExtendedHoursFuture`, `ExtendedHoursEtf`, `ExtendedHoursTopTicker`, `ExtendedHoursTweetStats`, `ExtendedHoursSnapshot`

- [ ] **Step 1: Append to `frontend/src/types.ts`**

Add after the last type definition:

```typescript
export type ExtendedHoursFuture = {
  label: string
  symbol: string
  price: number
  change_pct: number
}

export type ExtendedHoursEtf = {
  symbol: string
  price: number
  extended_price: number | null
  extended_change_pct: number | null
}

export type ExtendedHoursTopTicker = {
  ticker: string
  mentions: number
  sentiment: 'BULL' | 'BEAR' | 'NEUTRAL' | string
}

export type ExtendedHoursTweetStats = {
  total_mentions: number
  top_tickers: ExtendedHoursTopTicker[]
  sentiment_distribution: { BULL: number; BEAR: number; NEUTRAL: number }
}

export type ExtendedHoursSnapshot = {
  session: 'pre-market' | 'after-hours' | 'regular' | 'closed' | string
  window_start: string
  window_end: string
  futures: ExtendedHoursFuture[]
  etfs: ExtendedHoursEtf[]
  tweet_stats: ExtendedHoursTweetStats
}
```

- [ ] **Step 2: Type-check**

```
cd frontend && npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types.ts
git commit -m "feat: add ExtendedHoursSnapshot types"
```

---

## Task 5: `useExtendedHours` hook

**Files:**
- Create: `frontend/src/hooks/useExtendedHours.ts`

**Interfaces:**
- Consumes: `ExtendedHoursSnapshot` from Task 4
- Produces: `useExtendedHours() -> { data: ExtendedHoursSnapshot | null, loading: boolean, error: boolean }`

- [ ] **Step 1: Create `frontend/src/hooks/useExtendedHours.ts`**

```typescript
import { useEffect, useState } from 'react'
import type { ExtendedHoursSnapshot } from '../types'

const POLL_INTERVAL_MS = 3 * 60 * 1000 // 3 minutes

export function useExtendedHours() {
  const [data, setData]       = useState<ExtendedHoursSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(false)

  useEffect(() => {
    let cancelled = false

    const load = () => {
      const controller = new AbortController()

      fetch('/api/stocks/extended-hours', { signal: controller.signal })
        .then((res) => {
          if (!res.ok) throw new Error('extended-hours fetch failed')
          return res.json() as Promise<ExtendedHoursSnapshot>
        })
        .then((payload) => {
          if (cancelled) return
          setData(payload)
          setError(false)
        })
        .catch((err) => {
          if (cancelled || err.name === 'AbortError') return
          setError(true)
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })

      return controller
    }

    const controller = load()
    const id = setInterval(() => load(), POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      controller.abort()
      clearInterval(id)
    }
  }, [])

  return { data, loading, error }
}
```

- [ ] **Step 2: Type-check**

```
cd frontend && npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useExtendedHours.ts
git commit -m "feat: add useExtendedHours polling hook"
```

---

## Task 6: `ExtendedHoursPanel` component

**Files:**
- Create: `frontend/src/components/ExtendedHoursPanel.tsx`
- Create: `frontend/src/__tests__/ExtendedHoursPanel.test.tsx`

**Interfaces:**
- Consumes: `useExtendedHours` (Task 5); all four types from Task 4

- [ ] **Step 1: Write failing tests in `frontend/src/__tests__/ExtendedHoursPanel.test.tsx`**

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ExtendedHoursPanel from '../components/ExtendedHoursPanel'

const BASE_SNAPSHOT = {
  session: 'pre-market',
  window_start: '2026-06-23T04:00:00-04:00',
  window_end: '2026-06-23T09:30:00-04:00',
  futures: [
    { label: 'ES', symbol: 'CME_MINI:ES1!', price: 5800.0, change_pct: 0.31 },
    { label: 'NQ', symbol: 'CME_MINI:NQ1!', price: 20100.0, change_pct: 0.48 },
    { label: 'YM', symbol: 'CBOT_MINI:YM1!', price: 43000.0, change_pct: 0.22 },
  ],
  etfs: [
    { symbol: 'SPY', price: 580.0, extended_price: 581.5, extended_change_pct: 0.26 },
    { symbol: 'QQQ', price: 490.5, extended_price: 492.8, extended_change_pct: 0.47 },
    { symbol: 'IWM', price: 210.2, extended_price: null, extended_change_pct: null },
  ],
  tweet_stats: {
    total_mentions: 42,
    top_tickers: [{ ticker: 'NVDA', mentions: 10, sentiment: 'BULL' }],
    sentiment_distribution: { BULL: 20, BEAR: 10, NEUTRAL: 12 },
  },
}

function mockFetch(snapshot: object) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve({ ok: true, json: async () => snapshot } as Response)
    )
  )
}

describe('ExtendedHoursPanel', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('renders nothing during regular session', async () => {
    mockFetch({ ...BASE_SNAPSHOT, session: 'regular' })
    const { container } = render(<ExtendedHoursPanel />)
    await waitFor(() => expect(container.firstChild).toBeNull())
  })

  it('renders full panel during pre-market', async () => {
    mockFetch(BASE_SNAPSHOT)
    render(<ExtendedHoursPanel />)
    await waitFor(() => {
      expect(screen.getByText('Pre-market')).toBeInTheDocument()
      expect(screen.getByText('ES')).toBeInTheDocument()
      expect(screen.getByText('NQ')).toBeInTheDocument()
      expect(screen.getByText('SPY')).toBeInTheDocument()
      expect(screen.getByText('NVDA')).toBeInTheDocument()
      expect(screen.getByText(/42 mentions/)).toBeInTheDocument()
    })
  })

  it('renders full panel during after-hours', async () => {
    mockFetch({ ...BASE_SNAPSHOT, session: 'after-hours' })
    render(<ExtendedHoursPanel />)
    await waitFor(() => {
      expect(screen.getByText('After-hours')).toBeInTheDocument()
    })
  })

  it('renders collapsed chip during closed session and expands on click', async () => {
    mockFetch({ ...BASE_SNAPSHOT, session: 'closed' })
    render(<ExtendedHoursPanel />)

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /last session/i })).toBeInTheDocument()
    )

    fireEvent.click(screen.getByRole('button', { name: /last session/i }))

    await waitFor(() => {
      expect(screen.getByText('ES')).toBeInTheDocument()
    })
  })

  it('shows green for positive futures change', async () => {
    mockFetch(BASE_SNAPSHOT)
    render(<ExtendedHoursPanel />)
    await waitFor(() => screen.getByText('+0.31%'))
    const pct = screen.getByText('+0.31%')
    expect(pct.className).toMatch(/emerald|green/)
  })
})
```

- [ ] **Step 2: Run to confirm failure**

```
cd frontend && npm run test -- --reporter=verbose ExtendedHoursPanel
```

Expected: `FAILED` with `Cannot find module '../components/ExtendedHoursPanel'`

- [ ] **Step 3: Create `frontend/src/components/ExtendedHoursPanel.tsx`**

```tsx
import { useState } from 'react'
import type {
  ExtendedHoursEtf,
  ExtendedHoursFuture,
  ExtendedHoursSnapshot,
  ExtendedHoursTweetStats,
} from '../types'
import { useExtendedHours } from '../hooks/useExtendedHours'

function fmtPct(n: number): string {
  const sign = n >= 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

function fmtWindowTime(isoStart: string, isoEnd: string): string {
  const opts: Intl.DateTimeFormatOptions = {
    hour: 'numeric',
    minute: '2-digit',
    timeZone: 'America/New_York',
    hour12: true,
  }
  const start = new Date(isoStart).toLocaleTimeString('en-US', opts)
  const end   = new Date(isoEnd).toLocaleTimeString('en-US', opts)
  return `${start} – ${end} ET`
}

function sessionBadgeClass(session: string): string {
  if (session === 'pre-market')
    return 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
  if (session === 'after-hours')
    return 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300'
  return 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
}

function sessionLabel(session: string): string {
  if (session === 'pre-market') return 'Pre-market'
  if (session === 'after-hours') return 'After-hours'
  return session
}

function FutureCard({ f }: { f: ExtendedHoursFuture }) {
  const positive = f.change_pct >= 0
  return (
    <div className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
      <p className="text-xs font-semibold text-zinc-500 dark:text-zinc-400">{f.label}</p>
      <p className="mt-0.5 text-sm font-bold text-zinc-900 dark:text-zinc-100">
        {f.price.toLocaleString()}
      </p>
      <p className={`text-[11px] font-semibold ${positive ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
        {fmtPct(f.change_pct)}
      </p>
    </div>
  )
}

function EtfCard({ e }: { e: ExtendedHoursEtf }) {
  const hasExt = e.extended_price !== null && e.extended_change_pct !== null
  const extPositive = (e.extended_change_pct ?? 0) >= 0
  return (
    <div className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
      <p className="text-xs font-semibold text-zinc-500 dark:text-zinc-400">{e.symbol}</p>
      <p className="mt-0.5 text-sm font-bold text-zinc-900 dark:text-zinc-100">
        ${e.price.toFixed(2)}
      </p>
      {hasExt && (
        <p className={`text-[11px] font-semibold ${extPositive ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
          {e.extended_price!.toFixed(2)} · {fmtPct(e.extended_change_pct!)}
        </p>
      )}
    </div>
  )
}

function SentimentBar({ dist }: { dist: ExtendedHoursTweetStats['sentiment_distribution'] }) {
  const total = dist.BULL + dist.BEAR + dist.NEUTRAL
  if (total === 0) return null
  const bullPct    = (dist.BULL    / total) * 100
  const bearPct    = (dist.BEAR    / total) * 100
  const neutralPct = 100 - bullPct - bearPct
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full">
      <div style={{ width: `${bullPct}%` }}    className="bg-emerald-500" />
      <div style={{ width: `${neutralPct}%` }} className="bg-zinc-500" />
      <div style={{ width: `${bearPct}%` }}    className="bg-red-500" />
    </div>
  )
}

function sentimentDot(sentiment: string): string {
  if (sentiment === 'BULL') return 'bg-emerald-500'
  if (sentiment === 'BEAR') return 'bg-red-500'
  return 'bg-zinc-500'
}

function PanelBody({ snapshot }: { snapshot: ExtendedHoursSnapshot }) {
  const { session, window_start, window_end, futures, etfs, tweet_stats } = snapshot
  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${sessionBadgeClass(session)}`}>
          {sessionLabel(session)}
        </span>
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          {fmtWindowTime(window_start, window_end)}
        </span>
        <span className="ml-auto rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          Live
        </span>
      </div>

      {/* Futures */}
      {futures.length > 0 && (
        <div>
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">Futures</p>
          <div className="grid grid-cols-3 gap-2">
            {futures.map((f) => <FutureCard key={f.label} f={f} />)}
          </div>
        </div>
      )}

      {/* ETFs */}
      {etfs.length > 0 && (
        <div>
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">ETFs (extended)</p>
          <div className="grid grid-cols-3 gap-2">
            {etfs.map((e) => <EtfCard key={e.symbol} e={e} />)}
          </div>
        </div>
      )}

      {/* Tweet stats */}
      <div>
        <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
          {tweet_stats.total_mentions} mentions · {sessionLabel(session)} window
        </p>
        <div className="flex flex-wrap items-center gap-1.5">
          {tweet_stats.top_tickers.slice(0, 5).map((t) => (
            <span
              key={t.ticker}
              className="flex items-center gap-1 rounded-full border border-zinc-200 bg-zinc-50 px-2 py-0.5 text-[11px] font-semibold text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
            >
              <span className={`inline-block h-1.5 w-1.5 rounded-full ${sentimentDot(t.sentiment)}`} />
              {t.ticker}
              <span className="text-zinc-400">{t.mentions}</span>
            </span>
          ))}
        </div>
        <div className="mt-2">
          <SentimentBar dist={tweet_stats.sentiment_distribution} />
          <div className="mt-1 flex justify-between text-[10px] text-zinc-400">
            <span>Bull {tweet_stats.sentiment_distribution.BULL}</span>
            <span>Bear {tweet_stats.sentiment_distribution.BEAR}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function ExtendedHoursPanel() {
  const { data, loading } = useExtendedHours()
  const [expanded, setExpanded] = useState(false)

  if (loading || !data) return null
  if (data.session === 'regular') return null

  if (data.session === 'closed' && !expanded) {
    return (
      <div className="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950">
        <button
          type="button"
          aria-label="Expand last session recap"
          onClick={() => setExpanded(true)}
          className="flex w-full items-center justify-between text-sm text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
        >
          <span>Market closed · last session recap</span>
          <span className="text-xs">▼</span>
        </button>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      {data.session === 'closed' && (
        <div className="mb-3 flex items-center justify-between">
          <span className="text-xs text-zinc-400">Last session recap</span>
          <button
            type="button"
            onClick={() => setExpanded(false)}
            className="text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
          >
            ▲
          </button>
        </div>
      )}
      <PanelBody snapshot={data} />
    </div>
  )
}
```

- [ ] **Step 4: Run tests**

```
cd frontend && npm run test -- --reporter=verbose ExtendedHoursPanel
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ExtendedHoursPanel.tsx frontend/src/__tests__/ExtendedHoursPanel.test.tsx
git commit -m "feat: add ExtendedHoursPanel component with pre-market/after-hours/closed states"
```

---

## Task 7: Integration in `App.tsx` + build verification

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `ExtendedHoursPanel` from Task 6

- [ ] **Step 1: Add import to `frontend/src/App.tsx`**

Add to the imports section (with the other component imports):

```tsx
import ExtendedHoursPanel from './components/ExtendedHoursPanel'
```

- [ ] **Step 2: Insert `<ExtendedHoursPanel />` above `<StockMarketHoursBanner />`**

Find the `{route === 'stocks' && (` block in `App.tsx` (around line 577). Replace:

```tsx
            {route === 'stocks' && (
              <>
                <StockMarketHoursBanner />
```

with:

```tsx
            {route === 'stocks' && (
              <>
                <ExtendedHoursPanel />
                <StockMarketHoursBanner />
```

- [ ] **Step 3: Type-check and build**

```
cd frontend && npx tsc --noEmit && npm run build
```

Expected: no errors, build succeeds

- [ ] **Step 4: Run full frontend test suite**

```
cd frontend && npm run test
```

Expected: all tests pass

- [ ] **Step 5: Run full backend test suite**

```
pytest --maxfail=1 --disable-warnings -q
```

Expected: all tests pass

- [ ] **Step 6: Final commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: integrate ExtendedHoursPanel into stocks route"
```
