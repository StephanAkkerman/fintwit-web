# Frontend Integration Map

Last updated: 2026-04-09

## Mounted in `App.tsx` Today

Route-level sections:

- `/` (home)
  - `FearGreedWidget`
  - `RedditWsbWidget`
  - `MarketOverview`
  - Tweet timeline (`useTweets` + `TweetCard`)

- `/crypto`
  - `TrendingCryptoWidget`
  - `TreemapWidget`
  - Tweet timeline auto-filtered to crypto signals
  - Chart-focused sort controls: Latest / Charts first / Charts only

- `/stocks`
  - `StocktwitsWidget`
  - `SpyHeatmapWidget`
  - Tweet timeline auto-filtered to stock signals
  - Chart-focused sort controls: Latest / Charts first / Charts only

- `/portfolio`
  - `PortfolioPanel`
  - Add/list/toggle/delete IBKR-style stock positions
  - Summary cards backed by live valuation/PnL

- `/admin`
  - `DebugAdminPanel`
  - Purpose: inject synthetic tweets through `/api/debug/tweet` for ingestion/UX verification.

- `FearGreedWidget`
  - Fetches: `/api/fear-greed`
  - Purpose: sentiment snapshot card.

- Tweet timeline (`useTweets` + `TweetCard`)
  - Fetches: `/api/posts?limit=200` on initial mount, `/api/posts?limit=200&before_id=...` for manual older-page loading, and `/api/stream` (SSE)
  - Purpose: live timeline with native-style quote headers (quoted avatar + author + timestamp), quote embeds, media, in-page image lightbox previews, financial cards, chart badge signals, separate main/quoted sentiment badges, and engagement updates.
  - Quote integration: consumes `quoted_tweet` payload from backend for quote author metadata and quote media placement (falls back to markdown inference when absent).

- Sidebar filters
  - Category filters: all, crypto, stock, non-financial.
  - Ticker filters:
    - click ticker in tweet financial card,
    - type ticker manually and apply.

- `TreemapWidget` + `useTreemap`
  - Fetches: `/api/treemap`
  - Purpose: top crypto market-cap snapshot tiles.

- `TrendingCryptoWidget`
  - Fetches: `/api/trending-crypto`
  - Purpose: top searched crypto table with price and 24h change.

- `MarketOverview` + `useMarketAssets` + `AssetBadge`
  - Fetches: `/api/posts` + `/api/stream` (derived live assets)
  - Purpose: top streamed assets with live price/change links.

- `RedditWsbWidget` + `useRedditWsb`
  - Fetches: `/api/reddit/wsb?limit=...`
  - Purpose: latest WallStreetBets Reddit hot-post radar for headline and engagement context.

- `StocktwitsWidget` + `useStocktwits`
  - Fetches: `/api/stocktwits?keyword=...`
  - Purpose: StockTwits ranking view (trending / active / watched).

- `SpyHeatmapWidget` + `useSpyHeatmap`
  - Fetches: `/api/spy-heatmap?date=...`
  - Purpose: SPY constituent heatmap snapshot with selectable date ranges.

- `PortfolioPanel` + `usePortfolio`
  - Fetches: `/api/portfolio/positions` and `/api/portfolio/summary`
  - Mutates: `POST /api/portfolio/positions`, `PATCH /api/portfolio/positions/{position_id}`, `DELETE /api/portfolio/positions/{position_id}`
  - Purpose: manage IBKR stock positions and monitor live unrealized PnL.

## Not Yet Mounted

- No known unmounted widgets in `frontend/src/components/` for currently exposed market endpoints.

## Reuse Guidance

- Prefer adding new widgets as isolated components with a dedicated hook per endpoint.
- Keep endpoint contracts mirrored in `frontend/src/types.ts`.
- For any new endpoint connection, add:
  - one component-level test (render/data states),
  - one integration-style test in `App.test.tsx` if mounted in `App`.
