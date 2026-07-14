# Extended Hours Overview — Design Spec

**Date:** 2026-06-23  
**Status:** Approved  

## Summary

Add a contextual panel to the `/stocks` page that surfaces a pre-market or after-hours overview whenever the US market is outside regular trading hours. The panel shows US equity futures prices, key ETF extended-hours prices, and a tweet-mention stats digest for the current session window.

---

## Scope

| Session | Window | Panel state |
|---|---|---|
| Pre-market | 04:00–09:30 ET on trading days | Full panel |
| After-hours | 16:00–20:00 ET on trading days | Full panel |
| Regular | 09:30–16:00 ET | Hidden (returns `null`) |
| Closed (nights, weekends, holidays) | — | Collapsed chip with last-session recap |

---

## Backend

### New service: `app/services/extended_hours_service.py`

Responsible for:

1. **Window calculation** — uses `get_us_stock_session()` from `ticker-price-data` to determine the current session, then derives `window_start` / `window_end` as tz-aware ET datetimes:
   - `pre-market` → today 04:00 ET → today 09:30 ET
   - `after-hours` → today 16:00 ET → today 20:00 ET
   - `regular` / `closed` → most recently completed session window (so the collapsed recap still has data)

2. **Futures prices** — fetch ES1!, NQ1!, YM1! via `get_tradingview_quote` from `ticker-price-data`. Same `asyncio.Semaphore(4)` pattern as `_build_strip` in `app/api/overview.py`.

3. **ETF extended-hours prices** — fetch SPY, QQQ, IWM via `get_stock_info` from `ticker-price-data`. The Yahoo backend already returns `extended_price` / `extended_change_percent` when the session is non-regular.

4. **Cache** — single `asyncio.Lock`-guarded module-level cache with a 3-minute TTL. All three data sources are fetched together and cached as one payload.

### New tweet stats function: `get_extended_hours_stats` in `app/services/mention_aggregator.py`

Signature:
```python
async def get_extended_hours_stats(
    Session: async_sessionmaker,
    since_dt: datetime,
    until_dt: datetime,
    top_n: int = 10,
) -> dict
```

SQL query filters `tweets.created_at BETWEEN since_dt AND until_dt`, groups by ticker (via `json_each(assets)`), returns:
- `total_mentions` — count of distinct tweet-ticker pairs in window
- `top_tickers` — top N tickers by mention count, each with `{ ticker, mentions, sentiment }` where sentiment is the majority label derived from avg sentiment score
- `sentiment_distribution` — `{ BULL, BEAR, NEUTRAL }` counts across all mentions in the window

### New endpoint: `GET /api/stocks/extended-hours`

Added to the existing stocks router (wherever `/api/stocks/market-hours` is registered in `app/api/main.py`).

**Response schema (Pydantic):**
```python
class ExtendedHoursFuture(BaseModel):
    label: str           # "ES" / "NQ" / "YM"
    symbol: str          # TradingView symbol
    price: float
    change_pct: float

class ExtendedHoursEtf(BaseModel):
    symbol: str
    price: float
    extended_price: float | None
    extended_change_pct: float | None

class ExtendedHoursTopTicker(BaseModel):
    ticker: str
    mentions: int
    sentiment: str       # "BULL" | "BEAR" | "NEUTRAL"

class ExtendedHoursTweetStats(BaseModel):
    total_mentions: int
    top_tickers: list[ExtendedHoursTopTicker]
    sentiment_distribution: dict[str, int]  # {"BULL": n, "BEAR": n, "NEUTRAL": n}

class ExtendedHoursSnapshot(BaseModel):
    session: str         # "pre-market" | "after-hours" | "regular" | "closed"
    window_start: str    # ISO-8601 with tz
    window_end: str
    futures: list[ExtendedHoursFuture]
    etfs: list[ExtendedHoursEtf]
    tweet_stats: ExtendedHoursTweetStats
```

---

## Frontend

### New types in `frontend/src/types.ts`

```ts
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

### New hook: `frontend/src/hooks/useExtendedHours.ts`

- Fetches `GET /api/stocks/extended-hours` on mount
- Polls every 3 minutes via `setInterval`
- Returns `{ data: ExtendedHoursSnapshot | null, loading: boolean, error: boolean }`
- Follows the same pattern as `useStockMarketHours`

### New component: `frontend/src/components/ExtendedHoursPanel.tsx`

**Render logic:**
- `session === "regular"` → return `null`
- `session === "closed"` → render a single collapsed chip: `"Market closed · last session recap"` — clicking it expands to the full panel layout
- `session === "pre-market"` or `"after-hours"` → render full panel immediately

**Full panel layout (top to bottom):**

1. **Header row**
   - Session badge: amber (`bg-amber-900/40 text-amber-300`) for pre-market, violet (`bg-violet-900/40 text-violet-300`) for after-hours — same tokens as `StockMarketHoursBanner`
   - Window label: `"Pre-market · 4:00 AM – 9:30 AM ET"` (formatted from `window_start`/`window_end`)
   - "Live" pill on the right

2. **Futures row** — three compact cards (ES / NQ / YM)
   - Each: label, price, `change_pct` colored green/red

3. **ETFs row** — three compact cards (SPY / QQQ / IWM)
   - Each: symbol, regular close price, extended delta badge (`+1.8 / +0.31%`) — shown only when `extended_price` is non-null

4. **Tweet stats row**
   - Left: `"148 mentions · Pre-market window"`
   - Center: top-5 ticker chips, each with mention count + sentiment color dot (green=BULL, red=BEAR, zinc=NEUTRAL)
   - Right: inline proportional BULL / BEAR / NEUTRAL sentiment bar (three colored segments)

### Integration in `frontend/src/App.tsx`

Drop `<ExtendedHoursPanel />` at the top of the stocks route section, **above** `<StockMarketHoursBanner />`:

```tsx
{route === 'stocks' && (
  <>
    <ExtendedHoursPanel />
    <StockMarketHoursBanner />
    <StockHaltsWidget />
    ...
  </>
)}
```

---

## Data flow

```
useExtendedHours (polls every 3m)
  → GET /api/stocks/extended-hours
    → extended_hours_service.get_snapshot(Session)
        ├── get_us_stock_session()           → session + window bounds
        ├── get_tradingview_quote(ES/NQ/YM)  → futures prices
        ├── get_stock_info(SPY/QQQ/IWM)      → ETF extended prices
        └── get_extended_hours_stats(...)     → tweet mention digest
```

---

## Out of scope (deferred)

- Top stock movers by price change during the session (mentioned by user as "maybe later")
- Individual tweet display within the panel (user chose stats summary, not list)
- Crypto extended-hours equivalent (crypto trades 24/7, different concept)
