# Market Movers Panel — Design Spec

**Date:** 2026-06-26
**Branch base:** `feat/extended-hours-panel` (HEAD `09c7082`)
**Feature:** Always-visible pre-market and after-hours market movers panel on the `/stocks` route.

---

## Overview

A new panel on the stocks dashboard showing the top 10 biggest gainers and top 10 biggest losers in extended trading (pre-market or after-hours). The panel is always visible — during regular hours it shows the morning's pre-market movers; during closed/overnight it shows the last after-hours movers. Data is sourced from the TradingView Scanner API with a market-cap filter of > $100M.

---

## Architecture

### Session detection

The service picks which set of TradingView columns to query based on current New York time:

| ET hour range | Columns used | `session_type` label |
|---|---|---|
| 00:00 – 15:59 | `premarket_*` | `"pre-market"` |
| 16:00 – 23:59 | `postmarket_*` | `"after-hours"` |

This means during regular hours (09:30–16:00) the panel naturally shows "today's pre-market movers" without any special-casing. During closed/overnight it shows the retained after-hours values from the last session. TradingView retains these values on its scanner until they are overwritten by the next session.

### Data source

**TradingView Scanner API** — `POST https://scanner.tradingview.com/america/scan`

Two concurrent async requests per refresh:

**Gainers request:**
```json
{
  "filter": [
    { "left": "market_cap_basic", "operation": "greater", "right": 100000000 },
    { "left": "<prefix>_volume", "operation": "greater", "right": 0 },
    { "left": "<prefix>_change", "operation": "nempty" }
  ],
  "columns": ["name", "description", "close", "<prefix>_close", "<prefix>_change", "<prefix>_volume", "market_cap_basic"],
  "sort": { "sortBy": "<prefix>_change", "sortOrder": "desc" },
  "range": [0, 10]
}
```

**Losers request:** identical but `"sortOrder": "asc"`.

Where `<prefix>` is `premarket` or `postmarket` based on session detection above.

The `name` column returns the ticker symbol (e.g. `"AAPL"`); `description` returns the company name. The response `d` array maps 1:1 to the `columns` array. `premarket_change` / `postmarket_change` are percentage values (e.g. `1.23` = +1.23%).

No authentication required. No Playwright needed.

---

## Backend

### New file: `app/services/market_movers_service.py`

**Public API:**
```python
async def get_market_movers() -> dict | None
```

Returns:
```python
{
  "session_type": "pre-market" | "after-hours",
  "gainers": [MarketMoverDict, ...],   # 10 items, sorted best first
  "losers":  [MarketMoverDict, ...],   # 10 items, sorted worst first
}
```

Where `MarketMoverDict`:
```python
{
  "symbol":         str,   # e.g. "AAPL"
  "name":           str,   # e.g. "Apple Inc."
  "price":          float, # last regular-hours close
  "extended_price": float, # pre/postmarket close
  "change_pct":     float, # percentage, e.g. 1.23 for +1.23%
  "volume":         int,   # pre/postmarket volume
  "market_cap":     float, # market cap in USD
}
```

Returns `None` if both TradingView requests fail.

**Caching:** `asyncio.Lock` + module-level `tuple[float, dict | None]` with TTL of 300 seconds (5 minutes).

**Internal helpers:**
- `_current_prefix() -> str` — returns `"premarket"` or `"postmarket"` based on `datetime.now(ZoneInfo("America/New_York")).hour`
- `_build_payload(prefix: str, sort_order: str) -> dict` — builds the scanner POST body
- `_parse_rows(data: list, prefix: str) -> list[dict]` — maps scanner `d` arrays to `MarketMoverDict`
- `_fetch_movers(prefix: str) -> tuple[list, list]` — fires two concurrent requests, returns `(gainers, losers)`

### New endpoint in `app/api/main.py`

```python
@app.get("/api/stocks/market-movers")
async def stocks_market_movers(_=Depends(api_key_dep)):
    data = await get_market_movers()
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data
```

Placed after the existing `/api/stocks/extended-hours` endpoint.

### New test file: `tests/test_market_movers.py`

Tests (pytest-asyncio, monkeypatching `_fetch_movers`):
1. `test_get_market_movers_shape` — response has `session_type`, `gainers` (len 10), `losers` (len 10), each item has required keys
2. `test_get_market_movers_cache` — second call within TTL hits cache (fetch called once)
3. `test_market_movers_endpoint_returns_snapshot` — GET `/api/stocks/market-movers` returns 200 with correct shape
4. `test_market_movers_endpoint_503_when_none` — returns 503 when service returns `None`

---

## Frontend

### Updated `frontend/src/types.ts`

Append two new exported types:
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

### New file: `frontend/src/hooks/useMarketMovers.ts`

Polls `GET /api/stocks/market-movers` on mount and every 300,000 ms (5 minutes). Returns `{ data: MarketMoversSnapshot | null, loading: boolean, error: boolean }`. Uses AbortController + `cancelled` flag for cleanup. Same pattern as `useExtendedHours`.

### New file: `frontend/src/components/MarketMoversPanel.tsx`

**Always rendered** on the `/stocks` route (no session gating). Placed in `App.tsx` above `<ExtendedHoursPanel />`.

**Loading / error state:** returns `null` (no skeleton).

**Layout:**
- **Header row:** session badge chip (amber for `pre-market`, violet for `after-hours`) + title "Pre-market Movers" or "After-hours Movers"
- **Two-column table:** Gainers column (left, green `#` header) | Losers column (right, red `#` header)
- **Each row (10 rows per column):** rank number · symbol chip (monospace, dark pill) · company name (truncated, `max-w-[120px] truncate`) · extended price · change% (green if positive, red if negative) · volume (abbreviated: `≥1M → "1.2M"`, `≥1K → "1.2K"`)

**Helper functions:**
- `fmtVol(n: number): string` — abbreviates volume
- `fmtPct(n: number): string` — formats percentage with sign (e.g. `"+1.23%"`, `"-0.45%"`)
- `pctClass(n: number): string` — returns Tailwind color class (emerald for positive, red for negative)

**Colour tokens** (matching `StockMarketHoursBanner` and `ExtendedHoursPanel`):
- Pre-market badge: `bg-amber-900/40 text-amber-300`
- After-hours badge: `bg-violet-900/40 text-violet-300`

### New test file: `frontend/src/__tests__/MarketMoversPanel.test.tsx`

Uses `vi.stubGlobal('fetch', ...)` and `fireEvent` (not `userEvent`). Tests:
1. `renders null while loading` — fetch never resolves, container is empty
2. `renders gainers and losers columns` — snapshot with 2 gainers + 2 losers, checks for "Gainers" and "Losers" headers and at least one symbol
3. `shows pre-market badge for pre-market session_type` — checks amber class present
4. `shows after-hours badge for after-hours session_type` — checks violet class present
5. `formats positive change as green` — gainer with `change_pct: 1.23`, expects `+1.23%` with emerald/green class
6. `formats negative change as red` — loser with `change_pct: -0.87`, expects `-0.87%` with red class

### Updated `frontend/src/__tests__/App.test.tsx`

Add `/api/stocks/market-movers` mock to the existing fetch mock setup (returns `{ session_type: "pre-market", gainers: [], losers: [] }`) to prevent unhandled fetch errors in existing tests.

### Updated `App.tsx`

Add import and render `<MarketMoversPanel />` as the **first** child in the `route === 'stocks'` block, above `<ExtendedHoursPanel />`.

---

## Data flow

```
App.tsx (stocks route)
  └── <MarketMoversPanel />
        └── useMarketMovers (polls every 5 min)
              └── GET /api/stocks/market-movers
                    └── market_movers_service.get_market_movers()
                          ├── _current_prefix()  →  "premarket" | "postmarket"
                          ├── aiohttp POST (gainers)  ┐  asyncio.gather
                          └── aiohttp POST (losers)   ┘
                                └── scanner.tradingview.com/america/scan
```

---

## Error handling

- If either TradingView request fails (network error, non-200, malformed JSON): log the error, return `None` from `get_market_movers()`, endpoint returns 503.
- If only one of the two requests fails: still return `None` (partial data is misleading for a movers list).
- Frontend: `error: true` from hook → component returns `null` silently (no error banner needed; the panel simply doesn't appear).

---

## Out of scope

- Crypto market movers (separate concern, different scanner endpoint)
- Sorting/filtering controls in the UI
- Click-through to TradingView chart
- Historical movers (today only)
