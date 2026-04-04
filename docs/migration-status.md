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

## Connected End-to-End Today

- Tweet stream data: `/api/posts` + `/api/stream` -> timeline cards and filters.
- Fear & Greed widget: `/api/fear-greed` -> `FearGreedWidget`.

## Implemented in Code but Not Yet Mounted in Main Dashboard

- Treemap widget (`TreemapWidget`) and hook (`useTreemap`) for `/api/treemap`.
- Market overview widget (`MarketOverview`) and hook (`useMarketAssets`) derived from stream assets.
- Trending crypto widget (`TrendingCryptoWidget`) for `/api/trending-crypto`.

## Backend APIs Not Yet Connected in Main UI

- `/api/stocktwits`
- `/api/spy-heatmap`
- `/api/debug/tweet` (debug ingestion endpoint)

## Suggested Next Connections

- Add dashboard route/section for `StockTwits` rankings (`/api/stocktwits`).
- Add equity heatmap view for `/api/spy-heatmap`.
- Mount `TreemapWidget`, `TrendingCryptoWidget`, and `MarketOverview` in `App.tsx` or route-based pages.
