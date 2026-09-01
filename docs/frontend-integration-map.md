# Frontend Integration Map

Last updated: 2026-08-31

## Mounted in `App.tsx` Today

Infrastructure wiring note:

- Frontend Nginx proxy now uses Docker DNS dynamic re-resolution for backend upstream (`backend:7999`) on `/api/*` and `/api/stream`, preventing stale-upstream `502` behavior after backend container restarts.

Route-level sections:

- All non-admin routes (`/`, `/crypto`, `/stocks`, `/forex`, `/options`, `/portfolio`)
  - `TickerMentionsPanel`
  - Uses currently loaded timeline tweets for in-place mention analytics (top symbols, share, chart-linked density, active authors).
  - Analytics are reactive to route scope and sidebar user filtering.

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
  - `ForexMacroWidget`
  - `EconomicEventsWidget`
  - TradingView-backed US/EU yield curves, crypto indices, and stock/forex index snapshot
  - Investing high-impact macro calendar table
  - Tweet timeline auto-filtered to macro/forex signals
  - Chart-focused sort controls: Latest / Charts first / Charts only

- `/options`
  - `OptionsOverviewWidget`
  - Nasdaq-based options activity summary (calls/puts totals, put-call ratio, most-active contracts)
  - Tweet timeline sourced from options-only tweet feed (`/api/posts?...&options_only=true` + `/api/stream?options_only=true`)

- `/portfolio`
  - `PortfolioValueChart`
  - Portfolio value over time with selectable ranges (1W/1M/3M/6M/YTD/1Y/5Y/MAX), cost-basis reference line, and a table view
  - `PortfolioAssetInsights`
  - Per-asset ATH/ATL distance, 52-week range position, and highlight badges (at/near/recently at an extreme)
  - `PortfolioDiversification`
  - Sector allocation breakdown and a holding/sector concentration score (unrated/concentrated/moderate/diversified)
  - `IbkrPanel`
  - Live IBKR account summary, open positions, and today's executions
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
  - Fetches: `/api/posts?limit=200&since_hours=24` on initial mount, then keeps paging in 200-item batches until the selected time window is exhausted, while `/api/posts?limit=...&before_id=...` remains available for manual older-page loading, and `/api/stream` (SSE).
  - Options route variant: uses `options_only=true` on both REST + SSE feed calls so only options-classified tweets are loaded there.
  - Purpose: live timeline with native-style quote headers (quoted avatar + author + timestamp), repost attribution headers (original author identity + reposter line), subscriber-only post icons (main/repost/quoted when flagged), quote embeds, preserved body whitespace/line breaks, media, in-page image lightbox previews, compact financial cards (ticker + full name + type + linked price + last close + daily % change + optional TradingView TA rows + optional Signa signal row, both color-coded green/red/grey by direction), chart badge signals, separate main/quoted sentiment badges, options-intent metadata support (`is_options_tweet`, `options_context`), and engagement updates.
  - Quote integration: consumes `quoted_tweet` payload from backend for quote author metadata and quote media placement (falls back to markdown inference when absent).

- Sidebar filters
  - Category scope is controlled by route/section selection.
  - Subscriber-only toggle filters the active timeline to exclusive posts flagged `is_subscriber_only`.
  - Lookback controls:
    - toggle timeline window across `24h`, `48h`, and `7d` (`since_hours` values `24/48/168`),
    - display load-impact metrics (last load ms, fetched tweet count, loaded-in-memory count).
  - Ticker filters:
    - click ticker in tweet financial card,
    - type ticker manually and apply.
    - click ticker from `TickerMentionsPanel` bars/chips.
  - User filters:
    - click tweet author name/avatar,
    - type user name manually and apply.

- `TickerMentionsPanel`
  - Source data: route/user scoped subset of loaded timeline tweets from `useTweets`.
  - Purpose: visualize most mentioned symbols and quick mention statistics for the active scope.
  - Interaction: clicking an analytics ticker applies sidebar ticker filtering.

- `TreemapWidget` + `useTreemap`
  - Fetches: `/api/treemap`
  - Purpose: top crypto market-cap snapshot tiles.

- `TrendingCryptoWidget`
  - Fetches: `/api/trending-crypto`
  - Purpose: top searched crypto table with price and 24h change.

- `BinanceGainersLosersWidget` + `useBinanceGainersLosers`
  - Fetches: `/api/binance/gainers-losers`
  - Purpose: short-horizon crypto momentum panel with top gainers and losers from Binance USDT pairs.

- `MarketOverview` + `useMarketAssets` + `AssetBadge`
  - Fetches: `/api/posts` + `/api/stream` (derived live assets)
  - Purpose: top streamed assets with live current-price links, last-close context, and optional TradingView TA summary rows.

- `RedditWsbWidget` + `useRedditWsb`
  - Fetches: `/api/reddit/wsb?limit=...`
  - Purpose: latest WallStreetBets Reddit hot-post radar for headline and engagement context.

- `StocktwitsWidget` + `useStocktwits`
  - Fetches: `/api/stocktwits?keyword=...`
  - Purpose: StockTwits ranking view (trending / active / watched).

- `StockMarketHoursBanner` + `useStockMarketHours`
  - Fetches: `/api/stocks/market-hours`
  - Purpose: Display current major exchange session states, including pre-market/after-hours plus explicit closure context for weekends vs holidays (with holiday name when available).

- `StockHaltsWidget` + `useStockHalts`
  - Fetches: `/api/stock-halts`
  - Purpose: Display same-day Nasdaq halt rows with halt time and resumption time context.

- `OptionsOverviewWidget` + `useOptionsOverview`
  - Fetches: `/api/options/overview` (optional `symbols` query override)
  - Purpose: Display aggregated options activity (calls, puts, put-call ratio, bullish/bearish skew, most-active contracts).

- `EconomicEventsWidget` + `useEconomicEvents`
  - Fetches: `/api/events/economic?limit=...`
  - Purpose: Display upcoming high-impact US and Euro-zone economic events with flag emojis, impact badges, and actual/forecast/previous fields.

- `ForexMacroWidget` + `useForexMacroSnapshot`
  - Fetches: `/api/forex/macro`
  - Purpose: Display TradingView-backed US/EU yield curves, crypto indices, and the legacy stock/forex TradingView index panel for the macro route.

- `SpyHeatmapWidget` + `useSpyHeatmap`
  - Fetches: `/api/spy-heatmap?date=...`
  - Purpose: SPY constituent heatmap snapshot with selectable date ranges.

- `PortfolioPanel` + `usePortfolio`
  - Fetches: `/api/portfolio/positions` and `/api/portfolio/summary`
  - Mutates: `POST /api/portfolio/positions`, `PATCH /api/portfolio/positions/{position_id}`, `DELETE /api/portfolio/positions/{position_id}`
  - Purpose: manage IBKR stock positions and monitor live unrealized PnL.

- `PortfolioValueChart` + `usePortfolioHistory`
  - Fetches: `/api/portfolio/history?range=...` (polls every 5m; holds the previous render at reduced opacity while a new range loads)
  - Purpose: show portfolio value over time against cost basis, labelling each point as a recorded snapshot, a price reconstruction, or the live quote.

- `PortfolioAssetInsights` + `usePortfolioInsights`
  - Fetches: `/api/portfolio/insights` (polls every 5m)
  - Purpose: surface which holdings are at, near, or recently at an all-time high/low, plus their 52-week range position and weight.

- `PortfolioDiversification` + `usePortfolioInsights`
  - Fetches: `/api/portfolio/insights` (same hook/poll as `PortfolioAssetInsights`, no extra request)
  - Purpose: group holdings into sectors (equities/ETFs via GICS sector, other asset kinds via category) and show a balance label plus largest holding/sector, backed by a Herfindahl-Hirschman concentration score at both the holding and sector level.

## Not Yet Mounted

- No known unmounted widgets in `frontend/src/components/` for currently exposed market endpoints.

## Reuse Guidance

- Prefer adding new widgets as isolated components with a dedicated hook per endpoint.
- Keep endpoint contracts mirrored in `frontend/src/types.ts`.
- For any new endpoint connection, add:
  - one component-level test (render/data states),
  - one integration-style test in `App.test.tsx` if mounted in `App`.
