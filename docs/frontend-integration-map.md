# Frontend Integration Map

Last updated: 2026-04-12

## Mounted in `App.tsx` Today

Route-level sections:

- `/` (home)
  - `FearGreedWidget`
  - `RedditWsbWidget`
  - `MarketOverview`
  - Tweet timeline (`useTweets` + `TweetCard`)

- `/crypto`
  - `BinanceGainersLosersWidget`
  - `TrendingCryptoWidget`
  - `TreemapWidget`
  - Tweet timeline auto-filtered to crypto signals
  - Chart-focused sort controls: Latest / Charts first / Charts only

- `/stocks`
  - `StockMarketHoursBanner`
  - `StockHaltsWidget`
  - `StocktwitsWidget`
  - `SpyHeatmapWidget`
  - Tweet timeline auto-filtered to stock signals
  - Chart-focused sort controls: Latest / Charts first / Charts only

- `/forex`
  - `EconomicEventsWidget`
  - Investing high-impact macro calendar table
  - Tweet timeline auto-filtered to macro/forex signals
  - Chart-focused sort controls: Latest / Charts first / Charts only

- `/options`
  - `OptionsOverviewWidget`
  - Nasdaq-based options activity summary (calls/puts totals, put-call ratio, most-active contracts)
  - Tweet timeline auto-filtered to stock-linked symbols

- `/nfts`
  - `NftTrendingWidget`
  - CoinGecko trending NFT collections with floor-price pulse

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
  - Purpose: live timeline with native-style quote headers (quoted avatar + author + timestamp), repost attribution headers (original author identity + reposter line), subscriber-only post icons (main/repost/quoted when flagged), quote embeds, preserved body whitespace/line breaks, media, in-page image lightbox previews, compact financial cards (ticker + full name + type + linked price + daily % change), chart badge signals, separate main/quoted sentiment badges, and engagement updates.
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

- `BinanceGainersLosersWidget` + `useBinanceGainersLosers`
  - Fetches: `/api/binance/gainers-losers`
  - Purpose: short-horizon crypto momentum panel with top gainers and losers from Binance USDT pairs.

- `NftTrendingWidget` + `useTrendingNfts`
  - Fetches: `/api/nfts/trending?limit=...`
  - Purpose: NFT collection momentum table with floor price and 24h floor change.

- `MarketOverview` + `useMarketAssets` + `AssetBadge`
  - Fetches: `/api/posts` + `/api/stream` (derived live assets)
  - Purpose: top streamed assets with live price/change links.

- `RedditWsbWidget` + `useRedditWsb`
  - Fetches: `/api/reddit/wsb?limit=...`
  - Purpose: latest WallStreetBets Reddit hot-post radar for headline and engagement context.

- `StocktwitsWidget` + `useStocktwits`
  - Fetches: `/api/stocktwits?keyword=...`
  - Purpose: StockTwits ranking view (trending / active / watched).

- `StockMarketHoursBanner` + `useStockMarketHours`
  - Fetches: `/api/stocks/market-hours`
  - Purpose: Display current major exchange session states, including pre-market and after-hours.

- `StockHaltsWidget` + `useStockHalts`
  - Fetches: `/api/stock-halts`
  - Purpose: Display same-day Nasdaq halt rows with halt time and resumption time context.

- `OptionsOverviewWidget` + `useOptionsOverview`
  - Fetches: `/api/options/overview` (optional `symbols` query override)
  - Purpose: Display aggregated options activity (calls, puts, put-call ratio, bullish/bearish skew, most-active contracts).

- `EconomicEventsWidget` + `useEconomicEvents`
  - Fetches: `/api/events/economic?limit=...`
  - Purpose: Display upcoming high-impact US and Euro-zone economic events with flag emojis, impact badges, and actual/forecast/previous fields.

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
