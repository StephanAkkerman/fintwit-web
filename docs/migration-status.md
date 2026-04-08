# Migration Status

Last updated: 2026-04-06

## Backend: Implemented

- FastAPI app lifecycle with DB init and background tweet stream worker.
- API key dependency (`X-API-Key`) on all `/api/*` endpoints when `API_KEY` env var is set.
- Tweet ingestion and persistence from X timeline (`xclient`) with idempotent upsert.
- Symbol extraction fallback from tweet text (`$TICKER`, `#HASHTAG`) and symbol merge logic.
- Asset enrichment via `ticker-classifier` + Yahoo (equities) + CoinGecko (crypto).
- Crypto enrichment hardening: CoinGecko caching and Yahoo `-USD` fallback when CoinGecko returns rate-limit/transient failures.
- FinTwitBERT sentiment classification for streamed tweets with separate main-post and quoted-post outputs (main: `sentiment_*`, quoted: `quoted_sentiment_*`).
- Operational backfill command for historical tweet sentiment (`python -m app.runtime.backfill_sentiment`).
- SSE broadcasting (`/api/stream`) and engagement update handling for tweet updates.
- Service-backed endpoints for Fear & Greed, treemap, StockTwits, SPY heatmap, and trending crypto.
- Service-backed endpoints for Fear & Greed, treemap, StockTwits, SPY heatmap, trending crypto, and WallStreetBets Reddit hot posts.
- Reddit WallStreetBets ingestion uses asyncpraw-first (legacy-style credentials) with HTTP JSON fallback when credentials are missing.
- StockTwits service fallback for anti-bot blocks: curl-first fetch strategy with short-lived per-keyword cache fallback to avoid transient 503s (curl is executed via thread-backed sync subprocess for Windows/uvicorn compatibility).
- Portfolio backend for IBKR-style stock tracking: positions CRUD endpoints and live summary valuation/PnL using Yahoo quotes.
- Deployment scaffolding for self-hosting: backend Docker image, frontend Nginx reverse proxy for `/api/*` + `/api/stream`, Docker Compose stack for Raspberry Pi, and Terraform-managed Cloudflare tunnel + DNS.

## Frontend: Implemented

- Live tweet timeline using initial REST load + SSE updates.
- Timeline pagination: initial REST load now requests 200 tweets, with manual load-older pagination wired via `before_id`.
- Quote tweet markdown rendering with quote embed styling.
- Quote image handling inside embed (with main image placement before quote embed).
- Tweet images now open in an in-page lightbox preview (no full-page navigation away from timeline).
- Financial asset blocks in tweet cards (symbol, kind, name, price, daily %).
- Price links to source financial website when available.
- Sidebar filters: all, crypto, stock, non-financial.
- Ticker filtering via:
  - clicking ticker inside financial asset widget,
  - manual typed input in sidebar ticker filter.
- Route-level segmentation pages implemented:
  - `/` home overview,
  - `/crypto` crypto widgets,
  - `/stocks` stock widgets,
  - `/portfolio` portfolio management.
- Crypto and stock routes support chart-focused tweet ordering:
  - Latest,
  - Charts first,
  - Charts only.
- Tweet cards display a small "Chart" badge only when backend chart classification marks `has_chart=true`.
- Tweet cards display separate sentiment badges for the main post and quoted post using backend metadata.
- Portfolio route includes add/list/toggle/delete workflows and summary cards (positions, market value, cost basis, unrealized PnL).
- Home route includes a WallStreetBets radar widget with latest Reddit post momentum signals.

## Connected End-to-End Today

- Tweet stream data: `/api/posts` + `/api/stream` -> timeline cards, filters, and sentiment badges.
- Fear & Greed widget: `/api/fear-greed` -> `FearGreedWidget`.
- Treemap widget: `/api/treemap` -> `TreemapWidget`.
- Trending crypto widget: `/api/trending-crypto` -> `TrendingCryptoWidget`.
- StockTwits widget: `/api/stocktwits` -> `StocktwitsWidget`.
- SPY heatmap widget: `/api/spy-heatmap` -> `SpyHeatmapWidget`.
- Market overview stream assets: `/api/posts` + `/api/stream` -> `MarketOverview`.
- Debug admin panel: `/api/debug/tweet` -> `DebugAdminPanel` (`/admin`).
- Portfolio panel: `/api/portfolio/positions` + `/api/portfolio/summary` -> `PortfolioPanel` (`/portfolio`).
- WallStreetBets panel: `/api/reddit/wsb` -> `RedditWsbWidget` (`/`).

## Backend APIs Not Yet Connected in Main UI

- No known unconnected backend API endpoints from the current `app/api/main.py` surface.

## Suggested Next Connections

- Continue legacy feature migration from `fintwit-bot` domains not yet ported (forex, options, NFTs).
