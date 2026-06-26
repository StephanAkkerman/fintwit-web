# Market Movers Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an always-visible pre-market / after-hours market movers panel (top-10 gainers + losers) to the `/stocks` route, sourced from the TradingView Scanner API.

**Architecture:** A new `market_movers_service.py` POSTs two concurrent requests to `scanner.tradingview.com/america/scan` — one sorted desc (gainers), one asc (losers) — filtered to market cap > $100M. Session type is decided by current ET hour: < 16:00 → `premarket_*` columns, ≥ 16:00 → `postmarket_*` columns. A `MarketMoversPanel` React component polls a new `/api/stocks/market-movers` endpoint every 5 minutes and is always rendered on the stocks route (no session gating).

**Tech Stack:** Python 3.10+, aiohttp, zoneinfo, asyncio, FastAPI, pytest-asyncio; React 18, TypeScript strict, Vitest, @testing-library/react, Tailwind CSS.

## Global Constraints

- Python: `zoneinfo.ZoneInfo` for timezone (no pytz). aiohttp for HTTP. `asyncio.Lock` + module-level tuple cache, TTL 300 s.
- No Pandas DataFrames. No discord.py.
- TypeScript: strict mode, no `any`. `fireEvent` from `@testing-library/react` in all tests (never `userEvent`).
- Dark-mode-first Tailwind. Amber tokens (`bg-amber-900/40 text-amber-300`) for pre-market, violet (`bg-violet-900/40 text-violet-300`) for after-hours — must match `ExtendedHoursPanel.tsx` and `StockMarketHoursBanner.tsx`.
- All tests must pass before committing. Backend: `pytest --maxfail=1 --disable-warnings -q`. Frontend: `cd frontend && npm run test -- --reporter=verbose`.
- Branch: `feat/extended-hours-panel`.

---

### Task 1: market_movers_service.py

**Files:**
- Create: `app/services/market_movers_service.py`
- Create: `tests/test_market_movers_service.py`

**Interfaces:**
- Produces: `async def get_market_movers() -> dict | None`
  - Returns `{"session_type": "pre-market"|"after-hours", "gainers": list[dict], "losers": list[dict]}` or `None`
  - Each mover dict: `{"symbol": str, "name": str, "price": float, "extended_price": float, "change_pct": float, "volume": int, "market_cap": float}`
- Produces (for test patching): `async def _fetch_movers(prefix: str) -> tuple[list, list]`
- Produces (for test cache reset): `_cache: tuple[float, dict] | None` module variable

- [ ] **Step 1: Write the failing tests**

Create `tests/test_market_movers_service.py`:

```python
"""Tests for market_movers_service."""
import pytest
import app.services.market_movers_service as svc

pytestmark = pytest.mark.asyncio


def _make_mover(symbol: str, change_pct: float) -> dict:
    return {
        "symbol": symbol,
        "name": f"{symbol} Corp",
        "price": 100.0,
        "extended_price": 100.0 + change_pct,
        "change_pct": change_pct,
        "volume": 500_000,
        "market_cap": 5e9,
    }


FAKE_GAINERS = [_make_mover(f"G{i:02d}", float(i + 1)) for i in range(10)]
FAKE_LOSERS  = [_make_mover(f"L{i:02d}", float(-(i + 1))) for i in range(10)]


async def test_get_market_movers_shape(monkeypatch):
    monkeypatch.setattr(svc, "_cache", None)

    async def fake_fetch(prefix: str) -> tuple[list, list]:
        return FAKE_GAINERS, FAKE_LOSERS

    monkeypatch.setattr(svc, "_fetch_movers", fake_fetch)

    result = await svc.get_market_movers()

    assert result is not None
    assert result["session_type"] in ("pre-market", "after-hours")
    assert len(result["gainers"]) == 10
    assert len(result["losers"]) == 10
    for key in ("symbol", "name", "price", "extended_price", "change_pct", "volume", "market_cap"):
        assert key in result["gainers"][0], f"Missing key in gainer: {key}"
        assert key in result["losers"][0], f"Missing key in loser: {key}"


async def test_get_market_movers_cache(monkeypatch):
    monkeypatch.setattr(svc, "_cache", None)
    call_count = 0

    async def fake_fetch(prefix: str) -> tuple[list, list]:
        nonlocal call_count
        call_count += 1
        return FAKE_GAINERS, FAKE_LOSERS

    monkeypatch.setattr(svc, "_fetch_movers", fake_fetch)

    result1 = await svc.get_market_movers()
    result2 = await svc.get_market_movers()

    assert call_count == 1
    assert result1 is result2


async def test_get_market_movers_returns_none_when_fetch_fails(monkeypatch):
    monkeypatch.setattr(svc, "_cache", None)

    async def fake_fetch_fail(prefix: str) -> tuple[list, list]:
        raise RuntimeError("scanner unavailable")

    monkeypatch.setattr(svc, "_fetch_movers", fake_fetch_fail)

    result = await svc.get_market_movers()

    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_market_movers_service.py -v --disable-warnings
```

Expected: 3 failures with `ModuleNotFoundError` or `ImportError` (file doesn't exist yet).

- [ ] **Step 3: Implement the service**

Create `app/services/market_movers_service.py`:

```python
"""Market movers via TradingView Scanner API (pre-market and after-hours)."""

import asyncio
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
_SCANNER_URL = "https://scanner.tradingview.com/america/scan"
_CACHE_TTL = 300  # seconds
_cache: tuple[float, dict] | None = None
_lock = asyncio.Lock()


def _current_prefix() -> str:
    """Return 'postmarket' from 16:00 ET onward, else 'premarket'."""
    return "postmarket" if datetime.now(_ET).hour >= 16 else "premarket"


def _build_payload(prefix: str, sort_order: str) -> dict:
    return {
        "filter": [
            {"left": "market_cap_basic", "operation": "greater", "right": 100_000_000},
            {"left": f"{prefix}_volume", "operation": "greater", "right": 0},
            {"left": f"{prefix}_change", "operation": "nempty"},
        ],
        "columns": [
            "name",
            "description",
            "close",
            f"{prefix}_close",
            f"{prefix}_change",
            f"{prefix}_volume",
            "market_cap_basic",
        ],
        "sort": {"sortBy": f"{prefix}_change", "sortOrder": sort_order},
        "range": [0, 10],
    }


def _parse_rows(rows: list) -> list[dict]:
    result = []
    for item in rows:
        d = item.get("d", [])
        if len(d) < 7:
            continue
        symbol = (item.get("s") or "").split(":")[-1]
        result.append(
            {
                "symbol": symbol,
                "name": str(d[1] or d[0] or symbol),
                "price": float(d[2] or 0),
                "extended_price": float(d[3] or 0),
                "change_pct": float(d[4] or 0),
                "volume": int(d[5] or 0),
                "market_cap": float(d[6] or 0),
            }
        )
    return result


async def _fetch_movers(prefix: str) -> tuple[list, list]:
    async def _post(payload: dict) -> list:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _SCANNER_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                r.raise_for_status()
                body = await r.json(content_type=None)
                return body.get("data") or []

    gainers_raw, losers_raw = await asyncio.gather(
        _post(_build_payload(prefix, "desc")),
        _post(_build_payload(prefix, "asc")),
    )
    return _parse_rows(gainers_raw), _parse_rows(losers_raw)


async def get_market_movers() -> dict | None:
    global _cache
    async with _lock:
        if _cache is not None:
            ts, payload = _cache
            if time.time() - ts < _CACHE_TTL:
                return payload

        prefix = _current_prefix()
        session_type = "after-hours" if prefix == "postmarket" else "pre-market"

        try:
            gainers, losers = await _fetch_movers(prefix)
        except Exception:
            logger.exception("Failed to fetch market movers from TradingView scanner")
            return None

        payload = {
            "session_type": session_type,
            "gainers": gainers,
            "losers": losers,
        }
        _cache = (time.time(), payload)
        return payload


def _reset_cache_for_tests() -> None:
    global _cache
    _cache = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_market_movers_service.py -v --disable-warnings
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/market_movers_service.py tests/test_market_movers_service.py
git commit -m "feat: add market_movers_service with TradingView scanner and cache"
```

---

### Task 2: GET /api/stocks/market-movers endpoint

**Files:**
- Modify: `app/api/main.py` (add import + endpoint)
- Create: `tests/test_market_movers_api.py`

**Interfaces:**
- Consumes: `get_market_movers() -> dict | None` from Task 1
- Produces: `GET /api/stocks/market-movers` → 200 with snapshot dict, or 503

- [ ] **Step 1: Write the failing tests**

Create `tests/test_market_movers_api.py`:

```python
"""Tests for GET /api/stocks/market-movers."""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from app.api.main import app

pytestmark = pytest.mark.asyncio

_MOCK_PAYLOAD = {
    "session_type": "pre-market",
    "gainers": [
        {
            "symbol": "NVDA", "name": "NVIDIA Corp", "price": 900.0,
            "extended_price": 910.0, "change_pct": 1.11,
            "volume": 500_000, "market_cap": 2e12,
        }
    ],
    "losers": [
        {
            "symbol": "TSLA", "name": "Tesla Inc", "price": 200.0,
            "extended_price": 196.0, "change_pct": -2.0,
            "volume": 300_000, "market_cap": 6e11,
        }
    ],
}


async def test_market_movers_endpoint_returns_snapshot():
    app.state.API_KEY = ""
    with patch(
        "app.api.main.get_market_movers",
        new_callable=AsyncMock,
        return_value=_MOCK_PAYLOAD,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/api/stocks/market-movers")

    assert r.status_code == 200
    data = r.json()
    assert data["session_type"] == "pre-market"
    assert len(data["gainers"]) == 1
    assert data["gainers"][0]["symbol"] == "NVDA"
    assert len(data["losers"]) == 1


async def test_market_movers_endpoint_503_when_none():
    app.state.API_KEY = ""
    with patch(
        "app.api.main.get_market_movers",
        new_callable=AsyncMock,
        return_value=None,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/api/stocks/market-movers")

    assert r.status_code == 503
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_market_movers_api.py -v --disable-warnings
```

Expected: 2 failures — endpoint doesn't exist yet.

- [ ] **Step 3: Add import and endpoint to main.py**

Find the existing import for `get_extended_hours_snapshot` (around line 42 in `app/api/main.py`) and add directly below it:

```python
from ..services.market_movers_service import get_market_movers
```

Find the existing `/api/stocks/extended-hours` endpoint and add the new endpoint immediately after it:

```python
@app.get("/api/stocks/market-movers")
async def stocks_market_movers(_=Depends(api_key_dep)):
    data = await get_market_movers()
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_market_movers_api.py tests/test_market_movers_service.py -v --disable-warnings
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add app/api/main.py tests/test_market_movers_api.py
git commit -m "feat: add GET /api/stocks/market-movers endpoint"
```

---

### Task 3: Frontend types

**Files:**
- Modify: `frontend/src/types.ts` (append two types)

**Interfaces:**
- Produces: `MarketMover`, `MarketMoversSnapshot` — used by hook (Task 4) and component (Task 5)

- [ ] **Step 1: Append the types**

Open `frontend/src/types.ts` and append at the very end of the file:

```typescript
export type MarketMover = {
  symbol: string
  name: string
  price: number
  extended_price: number
  change_pct: number
  volume: number
  market_cap: number
}

export type MarketMoversSnapshot = {
  session_type: 'pre-market' | 'after-hours' | string
  gainers: MarketMover[]
  losers: MarketMover[]
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 0 errors in the new types (pre-existing errors in unrelated files are acceptable).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types.ts
git commit -m "feat: add MarketMover and MarketMoversSnapshot types"
```

---

### Task 4: useMarketMovers hook

**Files:**
- Create: `frontend/src/hooks/useMarketMovers.ts`

**Interfaces:**
- Consumes: `MarketMoversSnapshot` from Task 3
- Produces: `useMarketMovers() -> { data: MarketMoversSnapshot | null, loading: boolean, error: boolean }`

- [ ] **Step 1: Create the hook**

Create `frontend/src/hooks/useMarketMovers.ts`:

```typescript
import { useEffect, useState } from 'react'
import type { MarketMoversSnapshot } from '../types'

const POLL_INTERVAL_MS = 5 * 60 * 1000 // 5 minutes

export function useMarketMovers() {
  const [data, setData]       = useState<MarketMoversSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(false)

  useEffect(() => {
    let cancelled = false

    const load = () => {
      const controller = new AbortController()

      fetch('/api/stocks/market-movers', { signal: controller.signal })
        .then((res) => {
          if (!res.ok) throw new Error('market-movers fetch failed')
          return res.json() as Promise<MarketMoversSnapshot>
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

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 0 new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useMarketMovers.ts
git commit -m "feat: add useMarketMovers polling hook"
```

---

### Task 5: MarketMoversPanel component

**Files:**
- Create: `frontend/src/components/MarketMoversPanel.tsx`
- Create: `frontend/src/__tests__/MarketMoversPanel.test.tsx`

**Interfaces:**
- Consumes: `useMarketMovers()` from Task 4, `MarketMover`, `MarketMoversSnapshot` from Task 3
- Produces: `default export function MarketMoversPanel()` — used by Task 6 in App.tsx

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/__tests__/MarketMoversPanel.test.tsx`:

```typescript
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MarketMoversPanel from '../components/MarketMoversPanel'

const GAINER = {
  symbol: 'AAPL', name: 'Apple Inc.', price: 185.0,
  extended_price: 186.28, change_pct: 1.23, volume: 1_200_000, market_cap: 3e12,
}
const LOSER = {
  symbol: 'TSLA', name: 'Tesla Inc.', price: 200.0,
  extended_price: 198.26, change_pct: -0.87, volume: 850_000, market_cap: 6e11,
}

function makeSnapshot(overrides: object = {}) {
  return { session_type: 'pre-market', gainers: [GAINER], losers: [LOSER], ...overrides }
}

function mockFetch(snapshot: object) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ ok: true, json: async () => snapshot } as Response))
  )
}

describe('MarketMoversPanel', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('renders null while loading', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    const { container } = render(<MarketMoversPanel />)
    expect(container.firstChild).toBeNull()
  })

  it('renders gainers and losers columns', async () => {
    mockFetch(makeSnapshot())
    render(<MarketMoversPanel />)
    await waitFor(() => {
      expect(screen.getByText('Gainers')).toBeInTheDocument()
      expect(screen.getByText('Losers')).toBeInTheDocument()
      expect(screen.getByText('AAPL')).toBeInTheDocument()
      expect(screen.getByText('TSLA')).toBeInTheDocument()
    })
  })

  it('shows pre-market badge for pre-market session_type', async () => {
    mockFetch(makeSnapshot({ session_type: 'pre-market' }))
    render(<MarketMoversPanel />)
    await waitFor(() => {
      const badge = screen.getByText('Pre-market')
      expect(badge.className).toMatch(/amber/)
    })
  })

  it('shows after-hours badge for after-hours session_type', async () => {
    mockFetch(makeSnapshot({ session_type: 'after-hours' }))
    render(<MarketMoversPanel />)
    await waitFor(() => {
      const badge = screen.getByText('After-hours')
      expect(badge.className).toMatch(/violet/)
    })
  })

  it('formats positive change as green', async () => {
    mockFetch(makeSnapshot())
    render(<MarketMoversPanel />)
    await waitFor(() => {
      const pct = screen.getByText('+1.23%')
      expect(pct.className).toMatch(/emerald|green/)
    })
  })

  it('formats negative change as red', async () => {
    mockFetch(makeSnapshot())
    render(<MarketMoversPanel />)
    await waitFor(() => {
      const pct = screen.getByText('-0.87%')
      expect(pct.className).toMatch(/red/)
    })
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npm run test -- --reporter=verbose MarketMoversPanel
```

Expected: 6 failures — component file doesn't exist yet.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/MarketMoversPanel.tsx`:

```typescript
import type { MarketMover, MarketMoversSnapshot } from '../types'
import { useMarketMovers } from '../hooks/useMarketMovers'

function fmtVol(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function fmtPct(n: number): string {
  const sign = n >= 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

function pctClass(n: number): string {
  return n >= 0
    ? 'text-emerald-600 dark:text-emerald-400'
    : 'text-red-600 dark:text-red-400'
}

function sessionBadgeClass(sessionType: string): string {
  if (sessionType === 'pre-market')
    return 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
  if (sessionType === 'after-hours')
    return 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300'
  return 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
}

function MoverRow({ mover, rank }: { mover: MarketMover; rank: number }) {
  return (
    <tr className="border-b border-zinc-100 dark:border-zinc-800 last:border-0">
      <td className="py-1 pr-2 text-xs text-zinc-400 tabular-nums w-5">{rank}</td>
      <td className="py-1 pr-2">
        <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100">
          {mover.symbol}
        </span>
      </td>
      <td className="py-1 pr-2 max-w-[120px] truncate text-xs text-zinc-500 dark:text-zinc-400">
        {mover.name}
      </td>
      <td className="py-1 pr-2 text-xs text-right tabular-nums text-zinc-900 dark:text-zinc-100">
        ${mover.extended_price.toFixed(2)}
      </td>
      <td className={`py-1 pr-2 text-xs text-right tabular-nums font-semibold ${pctClass(mover.change_pct)}`}>
        {fmtPct(mover.change_pct)}
      </td>
      <td className="py-1 text-xs text-right tabular-nums text-zinc-500 dark:text-zinc-400">
        {fmtVol(mover.volume)}
      </td>
    </tr>
  )
}

function MoversTable({
  movers,
  label,
  headerClass,
}: {
  movers: MarketMover[]
  label: string
  headerClass: string
}) {
  return (
    <div className="flex-1 min-w-0">
      <p className={`mb-2 text-xs font-bold uppercase tracking-wide ${headerClass}`}>{label}</p>
      <table className="w-full">
        <tbody>
          {movers.map((m, i) => (
            <MoverRow key={m.symbol} mover={m} rank={i + 1} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function MarketMoversPanel() {
  const { data, loading } = useMarketMovers()

  if (loading || !data) return null

  const isPreMarket = data.session_type === 'pre-market'

  return (
    <div className="mb-4 rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mb-3 flex items-center gap-2">
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${sessionBadgeClass(data.session_type)}`}
        >
          {isPreMarket ? 'Pre-market' : 'After-hours'}
        </span>
        <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          {isPreMarket ? 'Pre-market Movers' : 'After-hours Movers'}
        </span>
      </div>
      <div className="flex gap-6">
        <MoversTable
          movers={data.gainers}
          label="Gainers"
          headerClass="text-emerald-600 dark:text-emerald-400"
        />
        <MoversTable
          movers={data.losers}
          label="Losers"
          headerClass="text-red-600 dark:text-red-400"
        />
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && npm run test -- --reporter=verbose MarketMoversPanel
```

Expected: 6 passed.

- [ ] **Step 5: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 0 new errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/MarketMoversPanel.tsx frontend/src/__tests__/MarketMoversPanel.test.tsx
git commit -m "feat: add MarketMoversPanel component with pre-market/after-hours states"
```

---

### Task 6: Integration in App.tsx + build verification

**Files:**
- Modify: `frontend/src/App.tsx` (import + render `<MarketMoversPanel />`)
- Modify: `frontend/src/__tests__/App.test.tsx` (add `/api/stocks/market-movers` mock)

**Interfaces:**
- Consumes: `MarketMoversPanel` default export from Task 5

- [ ] **Step 1: Add `/api/stocks/market-movers` mock to App.test.tsx**

In `frontend/src/__tests__/App.test.tsx`, find the block around line 47 that reads:

```typescript
if (url.includes('/api/stocks/extended-hours')) {
  return Promise.resolve(
    {
      ok: true,
      json: async () => ({
        session: 'regular',
        ...
      }),
    } as Response
  )
}
```

Immediately **after** the closing `}` of that block, add:

```typescript
if (url.includes('/api/stocks/market-movers')) {
  return Promise.resolve({
    ok: true,
    json: async () => ({ session_type: 'pre-market', gainers: [], losers: [] }),
  } as Response)
}
```

- [ ] **Step 2: Add import to App.tsx**

In `frontend/src/App.tsx`, find the import block with other component imports. Add `MarketMoversPanel` in alphabetical order among the capital-M imports:

```typescript
import MarketMoversPanel from './components/MarketMoversPanel'
```

- [ ] **Step 3: Render MarketMoversPanel in stocks route**

In `frontend/src/App.tsx`, find the block:

```tsx
{route === 'stocks' && (
```

The current first child is `<MarketMoversPanel />` (from the extended-hours feature — actually it's `<ExtendedHoursPanel />`). Add `<MarketMoversPanel />` as the **first** child, above `<ExtendedHoursPanel />`:

```tsx
{route === 'stocks' && (
  <>
    <MarketMoversPanel />
    <ExtendedHoursPanel />
    {/* ... rest of existing children ... */}
  </>
)}
```

Keep all existing children exactly as they are — only add `<MarketMoversPanel />` at the top.

- [ ] **Step 4: Run full frontend test suite**

```bash
cd frontend && npm run test -- --reporter=verbose
```

Expected: all tests pass (119+ tests). If App.test.tsx tests fail with unhandled fetch errors for `/api/stocks/market-movers`, go back and update the mock in Step 1.

- [ ] **Step 5: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 0 new errors.

- [ ] **Step 6: Production build**

```bash
cd frontend && npm run build
```

Expected: Build succeeds with no errors. Bundle size should be within ~10 KB of previous build.

- [ ] **Step 7: Run backend test suite**

```bash
pytest --maxfail=1 --disable-warnings -q
```

Expected: 1 pre-existing failure in `test_macro_market.py` (unrelated, exists on `main`). All market-movers tests pass.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/App.tsx frontend/src/__tests__/App.test.tsx
git commit -m "feat: integrate MarketMoversPanel into stocks route"
```
