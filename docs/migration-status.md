# Migration Status

Last updated: 2026-04-04

## Backend: Implemented

- FastAPI app lifecycle with DB init and background tweet stream worker.
- API key dependency (`X-API-Key`) on all `/api/*` endpoints when `API_KEY` env var is set.
- Tweet ingestion and persistence from X timeline (`xclient`) with idempotent upsert.
- Symbol extraction fallback from tweet text (`$TICKER`, `#HASHTAG`) and symbol merge logic.
- Asset enrichment via `ticker-classifier` + Yahoo (equities) + CoinGecko (crypto).
- SSE broadcasting (`/api/stream`) and engagement update handling for tweet updates.
- Service-backed endpoints for Fear & Greed, treemap, StockTwits, SPY heatmap, and trending crypto.
- StockTwits service fallback for anti-bot blocks: curl-first fetch strategy with short-lived per-keyword cache fallback to avoid transient 503s (curl is executed via thread-backed sync subprocess for Windows/uvicorn compatibility).

## Frontend: Implemented

- Live tweet timeline using initial REST load + SSE updates.
- Quote tweet markdown rendering with quote embed styling.
- Quote image handling inside embed (with main image placement before quote embed).
- Financial asset blocks in tweet cards (symbol, kind, name, price, daily %).
- Price links to source financial website when available.
- Sidebar filters: all, crypto, stock, non-financial.
- Ticker filtering via:
  - clicking ticker inside financial asset widget,
  - manual typed input in sidebar ticker filter.
- Route-level segmentation pages implemented:
  - `/` home overview,
  - `/crypto` crypto widgets,
  - `/stocks` stock widgets.

## Connected End-to-End Today

- Tweet stream data: `/api/posts` + `/api/stream` -> timeline cards and filters.
- Fear & Greed widget: `/api/fear-greed` -> `FearGreedWidget`.
- Treemap widget: `/api/treemap` -> `TreemapWidget`.
- Trending crypto widget: `/api/trending-crypto` -> `TrendingCryptoWidget`.
- StockTwits widget: `/api/stocktwits` -> `StocktwitsWidget`.
- SPY heatmap widget: `/api/spy-heatmap` -> `SpyHeatmapWidget`.
- Market overview stream assets: `/api/posts` + `/api/stream` -> `MarketOverview`.

## Backend APIs Not Yet Connected in Main UI

- `/api/debug/tweet` (debug ingestion endpoint)

## Suggested Next Connections

- Add a lightweight admin/debug panel for `/api/debug/tweet` injection workflow.
