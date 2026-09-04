# Frontend Integration Map

Last updated: 2026-09-04

## Mounted in `App.tsx` Today

Infrastructure wiring note:

- Frontend Nginx proxy now uses Docker DNS dynamic re-resolution for backend upstream (`backend:7999`) on `/api/*` and `/api/stream`, preventing stale-upstream `502` behavior after backend container restarts.

Route-level sections:

- Non-home, non-admin, non-signa routes (`/crypto`, `/stocks`, `/forex`, `/options`, `/portfolio`)
  - `MentionHeatmap` (route-scoped `assetKind`: `CRYPTO` for `/crypto`, `FOREX` for `/forex`, `EQUITY` for `/stocks` and `/portfolio`, `all` for `/options`)
  - Backend-aggregated mention/sentiment/price data from `/api/overview/mention-heat`, reactive to sidebar user filtering.
  - Replaces the old `TickerMentionsPanel` (issue #94: it duplicated the heatmap while showing less useful, client-computed stats from only the currently loaded tweet buffer).

- `/` (home) already renders the same heatmap (assetKind `all`, with asset/window tabs) via `OverviewDashboard`, so no separate top panel is shown there.

- `/` (home)
  - `FearGreedWidget`
  - `RedditWsbWidget`
  - `MarketOverview`
  - `OverviewDashboard` — macro strip (`MacroStrip`), the `all`-scoped `MentionHeatmap`, a three-column analytics row (`SentimentShiftWidget`, `VolumeBaselineWidget`, `HiddenGemWidget`), and `SectorMentionsWidget`, with shared asset-kind (`all`/`EQUITY`/`CRYPTO`/`FOREX`) and lookback-window (24h/48h/7d) controls
  - Tweet timeline (`useTweets` + `TweetCard`)

- `/crypto`
  - `BinanceGainersLosersWidget`
  - `TrendingCryptoWidget`
  - `TreemapWidget`
  - Tweet timeline auto-filtered to crypto signals
  - Chart-focused sort controls: Latest / Charts first / Charts only

- `/stocks`
  - `StockFearGreedWidget`
  - `StockMarketHoursBanner`
  - `StockHaltsWidget`
  - `StocktwitsWidget`
  - `SpyHeatmapWidget`
  - `EarningsCalendarWidget`
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

- `/traders`
  - `TraderLeaderboardWidget`
  - Purpose: trader credibility leaderboard (issue #72, narrowed scope). A horizon tab (1/7/30 days) over a table ranked by hit-rate, with graded-call count and signed average return. Self-contained like `/signa` — not wired into the shared tweet timeline, ticker/user filters, or the cross-route `MentionHeatmap`/`RouteSignalsPanel` block.
  - Fetches: `/api/traders/leaderboard` via `useTraderLeaderboard`.

- `/admin`
  - `DebugAdminPanel`
  - Purpose: inject synthetic tweets through `/api/debug/tweet` for ingestion/UX verification.

- `FearGreedWidget`
  - Fetches: `/api/fear-greed`
  - Purpose: sentiment snapshot card.

- `StockFearGreedWidget`
  - Fetches: `/api/stocks/fear-greed`
  - Purpose: stock market Fear & Greed index card (value + rating + day-over-day change), mounted on `/stocks`.

- Tweet timeline (`useTweets` + `TweetCard`)
  - Fetches: `/api/posts?limit=200&since_hours=24` on initial mount, then keeps paging in 200-item batches until the selected time window is exhausted, while `/api/posts?limit=...&before_id=...` remains available for manual older-page loading, and `/api/stream` (SSE).
  - Options route variant: uses `options_only=true` on both REST + SSE feed calls so only options-classified tweets are loaded there.
  - Purpose: live timeline with native-style quote headers (quoted avatar + author + timestamp), repost attribution headers (original author identity + reposter line), subscriber-only post icons (main/repost/quoted when flagged), quote embeds, preserved body whitespace/line breaks, media, in-page image lightbox previews, compact financial cards (ticker + full name + type + linked price + last close + daily % change + optional TradingView TA rows + optional Signa signal row + optional StockTwits sentiment row, all color-coded by direction/dominant side), chart badge signals, a chart-extracted symbol/timeframe/price badge for tickerless chart tweets (issue #49), separate main/quoted sentiment badges, options-intent metadata support (`is_options_tweet`, `options_context`), portfolio-status badges (💼 Held / 🕓 Recently Held) on financial cards whose ticker matches a portfolio position, and engagement updates.
  - Quote integration: consumes `quoted_tweet` payload from backend for quote author metadata and quote media placement (falls back to markdown inference when absent).
  - Portfolio badge integration: `App.tsx` calls `usePortfolioTickers` (fetches `/api/portfolio/positions`, polls every 5m) and passes the resulting `portfolioLookup` into every `TweetCard`. A ticker is "Held" if any position for that symbol has `is_active: true`, or "Recently Held" if its most recent closed position's `updated_at` is within the last 30 days; otherwise no badge is shown.

- Sidebar filters
  - Category scope is controlled by route/section selection.
  - Subscriber-only toggle filters the active timeline to exclusive posts flagged `is_subscriber_only`.
  - Lookback controls:
    - toggle timeline window across `24h`, `48h`, and `7d` (`since_hours` values `24/48/168`),
    - display load-impact metrics (last load ms, fetched tweet count, loaded-in-memory count).
  - Ticker filters:
    - click ticker in tweet financial card,
    - type ticker manually and apply.
    - click a `MentionHeatmap` tile.
  - User filters:
    - click tweet author name/avatar,
    - type user name manually and apply.
  - Every ticker click above (financial card, cashtag, hashtag, `MentionHeatmap` tile) also opens `TickerDetailModal`, in addition to applying the sidebar ticker filter.

- `MentionHeatmap` (route-scoped, outside `/`)
  - Source data: `/api/overview/mention-heat`, scoped by route `assetKind` and the sidebar user filter.
  - Purpose: visualize most mentioned symbols (sized by mentions, colored by sentiment, ringed by price direction) for the active scope.
  - Interaction: clicking a tile applies sidebar ticker filtering and opens `TickerDetailModal`.

- `TickerDetailModal` + `useTickerTimeseries`
  - Fetches: `/api/overview/ticker-timeseries?ticker=...&window_hours=...`.
  - Purpose: per-ticker deep dive (issue #108) — mentions-over-time chart with an average-mentions reference line, a stacked bullish/bearish/neutral bar chart, and summary stat tiles (total mentions, avg mentions/bucket, overall sentiment, price move, unique voices, chart-tagged tweets, avg engagement, asset kind).
  - Interaction: opened from `App.tsx`'s `onTickerSelect` (the same callback every ticker click site already calls), with a 24h/7d/30d window toggle; closes on the Close button, backdrop click, or Escape.
  - Mounted app-wide as a modal overlay (not a route), consistent with the existing tweet-media lightbox pattern in `TweetCard`.

- `SectorMentionsWidget` + `useSectorMentions` (`/` only, inside `OverviewDashboard`)
  - Fetches: `/api/overview/sector-mentions?window_hours=...` (plus the sidebar user filter).
  - Purpose: most-mentioned equity sectors (issue #104) — proportional bars ranked by the fairness-adjusted `mention_score`, top mentioned tickers per sector, expandable per-sector industry breakdown (e.g. "Technology > Semiconductors"). Equity-only: crypto/forex tickers carry no sector metadata, so it is not asset-kind scoped like the other overview widgets.
  - Interaction: expand/collapse a sector row for its industries; clicking a ticker chip applies sidebar ticker filtering and opens `TickerDetailModal` via the shared `onTickerClick` callback.

- `MacroStrip` + `useMacroStrip` (`/` only, inside `OverviewDashboard`)
  - Fetches: `/api/overview/macro-strip` (5-minute server-side cache).
  - Purpose: at-a-glance macro tape — live price + % change + sparkline tiles for SPX, NDX, BTC, ETH, DXY, VIX, and GOLD — above the rest of the home dashboard.

- `SentimentShiftWidget` + `useSentimentShift` (`/` only, inside `OverviewDashboard`)
  - Fetches: `/api/overview/sentiment-shift`, scoped by the dashboard's asset-kind/window controls and the sidebar user filter.
  - Purpose: rank tickers by the biggest swing in average tweet sentiment between the active window and the prior baseline, each row showing a prev→current sentiment sparkline and signed delta — surfaces sentiment momentum, not just mention volume.
  - Portfolio awareness: accepts the shared `portfolioLookup` (see below) and renders a `PortfolioTickerBadge` next to any ticker currently or recently held.

- `VolumeBaselineWidget` + `useVolumeBaseline` (`/` only, inside `OverviewDashboard`)
  - Fetches: `/api/overview/volume-baseline`, same scoping as `SentimentShiftWidget`.
  - Purpose: "Unusually loud" — tickers whose mention count in the active window exceeds a multiple of their rolling baseline rate, each row showing mentions vs. baseline and the multiplier — mention-spike/anomaly detection.
  - Portfolio awareness: same `portfolioLookup` badge as `SentimentShiftWidget`.

- `HiddenGemWidget` + `useHiddenGems` (`/` only, inside `OverviewDashboard`)
  - Fetches: `/api/overview/hidden-gems`, same scoping as `SentimentShiftWidget`.
  - Purpose: surface tickers being mentioned for the first time (✦ new) or resurfacing after a long gap (↩ resurface) in the active window — catches tickers before they're loud enough to rank on the main mention heatmap.
  - Portfolio awareness: same `portfolioLookup` badge as `SentimentShiftWidget`.

- `PortfolioTickerBadge` (shared by `SentimentShiftWidget`, `VolumeBaselineWidget`, `HiddenGemWidget`)
  - Consumes: the same `portfolioLookup` function (`usePortfolioTickers`, computed once in `App.tsx` and threaded through `OverviewDashboard`) that already badges tweet-card financial cards as 💼 Held / 🕓 Recently Held.
  - Purpose: compact emoji-only variant of the same portfolio-status signal for the tighter analytics-row layouts, so a sentiment swing, mention spike, or hidden gem on a held position is visible without leaving the home dashboard.

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

- `SectorOverviewWidget` + `useSectorOverview`
  - Fetches: `/api/spy-heatmap/sectors?date=...`
  - Purpose: SPY sector/subsector performance trends (e.g. Technology, and within it Semiconductors vs Software) with selectable date ranges; each sector expands to its subsector breakdown.

- `EarningsCalendarWidget` + `useEarningsCalendar` (`/stocks`)
  - Fetches: `/api/earnings/calendar?days=7`.
  - Purpose: horizontally-scrollable strip of the next 7 days, each a card listing that day's reporting tickers (already ranked by market cap), a session emoji (🌅 pre-market / 🌙 after-hours), and the EPS estimate; a day with nothing scheduled shows "No major earnings" instead of being omitted, and a day with more tickers than fit shows a "+N more" note.
  - Portfolio awareness: accepts `portfolioLookup` (passed from `App.tsx`, same source as the tweet-card Held/Recently Held badges) and renders a `PortfolioTickerBadge` next to any reporting ticker currently or recently held — so an upcoming earnings date on one of your own positions stands out from the rest of the calendar.

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
