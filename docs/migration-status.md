# Migration Status

Last updated: 2026-06-17

## Backend: Implemented

- Ticker pricing extracted to the external [`ticker-price-data`](https://github.com/StephanAkkerman/ticker-price-data) package (Yahoo/CoinGecko/TradingView + unified `get_price`). The old `app/services/{yahoo,coingecko,tradingview_quote,tradingview_stream}.py` modules were removed; consumers import from `ticker_price_data`. CoinGecko now uses the website `search_v2` endpoint to avoid public-API rate limits.

- FastAPI app lifecycle with DB init and background tweet stream worker.
- API key dependency (`X-API-Key`) on all `/api/*` endpoints when `API_KEY` env var is set.
- Tweet ingestion and persistence from X timeline (`xclient`) with idempotent upsert.
- Symbol extraction fallback from tweet text (`$TICKER`, `#HASHTAG`) and symbol merge logic.
- Asset enrichment via `ticker-classifier` + Yahoo (equities) + CoinGecko (crypto).
- Asset enrichment hardening: uses classifier `yahoo_lookup` with centralized shortcut mappings in `ticker-classifier` (e.g. `DXY` -> `DX-Y.NYB`) so ETF/index/forex-style symbols are more reliably priced/classified.
- Asset enrichment local symbol overrides: ambiguous symbols now use deterministic mappings before pricing/classification (`ETH` forced to `CRYPTO`; `EURUSD` -> `EURUSD=X`; `USOIL` -> `CL=F`).
- Quote fallback hardening: when Yahoo/CoinGecko are rate-limited or unavailable, enrichment now attempts TradingView quote fallback before returning no price data.
- Quote source marker: enriched financial payload now includes `source` so frontend can display the provider used (`yahoo`, `coingecko`, `tradingview`).
- Yahoo quote enrichment now prefers the latest session trade as `price` and also exposes `last_close` for pre-market/after-hours cards.
- TradingView technical analysis summaries (4H and 1D) are now attached to enriched tweet asset financial payloads under `technical_analysis` for ticker widgets.
- Signa signal verdicts are now attached to enriched tweet asset financial payloads under `signa` (verdict label, score, trend, confidence) for equity-like kinds only (`EQUITY`, `ETF`, `INDEX`, `FUTURE`).
- Asset noise reduction: unsupported/unknown classifier kinds are now excluded from tweet `assets`, so non-financial hashtags (for example topic tags) are not rendered as unknown ticker assets.
- Asset extraction signal tightening: enrichment now uses cashtags/tickers only (not hashtags) so topic hashtags (for example `#OOTT`, `#Tankers`) do not generate asset cards.
- Equity asset enrichment now includes optional `sector` and `industry` metadata (for example `AAPL`/`NVDA` tagged as technology) sourced from classifier metadata.
- Equity/ETF asset enrichment now includes optional `company_profile` metadata (`industry_group`, `country`, `exchange`, `currency`, `website`, `market_cap_category`) from classifier metadata.
- Asset enrichment now includes an optional `fundamentals` block (`market_cap`, `forward_pe`, `trailing_pe`, `eps_forward`, `eps_trailing`, `avg_volume`, `avg_volume_10d`, `currency`) extracted from the Yahoo quote `ticker-classifier` already fetches, so it adds no network calls. Market cap, forward P/E (falling back to trailing P/E), average volume and the industry/sector are now shown by default on tweet asset cards alongside the technical-analysis rows. Forward P/E (and the trailing fallback) is colour-coded green at or under 15x, red at or over 30x, grey between, via the generic `utils/metricQuality` three-band scale.
- Crypto enrichment hardening: CoinGecko caching and Yahoo `-USD` fallback when CoinGecko returns rate-limit/transient failures.
- FinTwitBERT sentiment classification for streamed tweets with separate main-post and quoted-post outputs (main: `sentiment_*`, quoted: `quoted_sentiment_*`).
- Full nested quoted tweet payload passthrough (`quoted_tweet`) from xtimeline is now persisted and served via `/api/posts`/`/api/stream`.
- Operational backfill command for historical tweet sentiment (`python -m app.runtime.backfill_sentiment`).
- SSE broadcasting (`/api/stream`) and engagement update handling for tweet updates.
- Service-backed endpoints for Fear & Greed, treemap, StockTwits, SPY heatmap, and trending crypto.
- Signa service client coverage expanded for `/api/v1/signal`, `/api/v1/quote/{ticker}`, `/api/v1/history/{ticker}`, `/api/v1/enhanced-signal`, `/api/v1/signal-index`, `/api/v1/scan`, and `/api/v1/me` (with retained legacy analysis helper for compatibility). The client is now fully async (`aiohttp`, non-blocking) with an `asyncio` cache/quota guard, and exposes a `get_signa_signal()` helper for enrichment.
- Signa `/signa` route is now a two-layer tabbed section: "Best Trades" (daily consensus, `/api/signa/best-trades` → `app.getsigna.ai/api/signals/run`) and "Live Feed" (raw per-model live signals, `/api/signa/live-feed` → `app.getsigna.ai/api/signals/feed`). The live feed is filtered to directional calls only (BUY/SELL/SHORT), ranked with the same comparator as Best Trades (score → confidence → tier), and auto-refreshes every 5 minutes via `useSignaLiveFeed`.
- Additional market-microstructure endpoints now available: Binance gainers/losers (`/api/binance/gainers-losers`) and Nasdaq stock halts (`/api/stock-halts`).
- Options migration slice: market options overview endpoint (`/api/options/overview`) now available, powered by Nasdaq most-active option-chain data for major US underlyings.
- Stream/runtime options-intent classification now tags tweets with `is_options_tweet` and structured `options_context` (contracts/side/score) for options-focused filtering and UI routing.
- Options tweet delivery now supports backend feed filtering (`options_only=true`) on both `/api/posts` and `/api/stream` for route-level isolation.
- Stock migration slice: market session endpoint (`/api/stocks/market-hours`) now available with pre-market/after-hours state mapping for major exchanges.
- Stock market-hours endpoint now derives schedules from `exchange_calendars` and includes explicit closed-session context (`closure_reason`, `is_holiday`, optional `holiday_name`) so holiday closures can be distinguished from weekends.
- Events migration slice: Investing economic calendar endpoint (`/api/events/economic`) now available for high-impact US and Euro-zone events.
- Forex/macro migration slice: TradingView-backed macro snapshot endpoint (`/api/forex/macro`) now exposes US/EU yield curves plus major FX index quotes for the `/forex` route.
- Forex/macro migration slice: the macro snapshot now also includes legacy crypto indices and the stock/forex TradingView index panel, with market-hours-aware visibility for the legacy stock/forex block.
- Service-backed endpoints for Fear & Greed, treemap, StockTwits, SPY heatmap, trending crypto, and WallStreetBets Reddit hot posts.
- Reddit WallStreetBets ingestion uses asyncpraw-first (legacy-style credentials) with HTTP JSON fallback when credentials are missing.
- StockTwits service fallback for anti-bot blocks: curl-first fetch strategy with short-lived per-keyword cache fallback to avoid transient 503s (curl is executed via thread-backed sync subprocess for Windows/uvicorn compatibility).
- Portfolio backend for IBKR-style stock tracking: positions CRUD endpoints and live summary valuation/PnL using Yahoo quotes.
- Deployment scaffolding for self-hosting: backend Docker image, frontend Nginx reverse proxy for `/api/*` + `/api/stream`, Docker Compose stack for Raspberry Pi, and Terraform-managed Cloudflare tunnel + DNS.
- Frontend proxy resilience hardening: containerized Nginx now uses Docker DNS re-resolution for backend upstream (`backend:7999`) so backend restarts do not leave stale upstream IPs that can surface first-hit `502` responses.

## Frontend: Implemented

- Live tweet timeline using initial REST load + SSE updates.
- Timeline pagination: initial REST load pages in fixed batches and keeps requesting older pages until the selected time window is exhausted, while manual load-older pagination still uses `before_id`.
- Sidebar lookback toggle now supports 24h/48h/7d windows and triggers immediate timeline reloads so users can compare data volume and load-speed impact.
- Sidebar performance mini-metrics now show last load duration, fetched tweet count, and currently loaded in-memory count for quick impact checks while changing lookback windows.
- Sidebar subscriber-only toggle now filters the loaded timeline down to exclusive posts, including quoted subscriber-only posts when present.
- Quote tweet markdown rendering with quote embed styling.
- Repost handling: retweeted posts now render with original author identity (name/avatar) and explicit reposter attribution line.
- Quote tweet header now mirrors native X styling by showing quoted author identity (instead of a generic label) and quoted timestamp when available.
- Quote tweet header now includes the quoted user's avatar next to their name when image metadata is available.
- Quote embeds now consume backend `quoted_tweet` metadata/media directly (author, handle, timestamp, image), with markdown heuristics only as fallback.
- Subscriber-only posts now render a native-style icon in tweet headers (including reposted originals and quoted tweet headers when marked exclusive).
- Quote image handling inside embed (with main image placement before quote embed).
- Tweet body rendering now preserves original line breaks and intentional blank lines.
- Tweet images now open in an in-page lightbox preview (no full-page navigation away from timeline).
- Tweet timestamps are shown in the viewer's local timezone (UTC source timestamps normalized server-side with explicit UTC offset).
- Financial asset blocks in tweet cards are intentionally compact and now show ticker, full name, type, current price, last close when available, daily % change, and optional TradingView TA summary rows.
- Price links to source financial website when available.
- Sidebar category filter widget removed; route sections now drive category scope.
- Sidebar subscriber-only toggle filters the loaded timeline to posts marked `is_subscriber_only`.
- Ticker filtering via:
  - clicking ticker inside financial asset widget,
  - manual typed input in sidebar ticker filter.
- User filtering via:
  - clicking tweet author name or avatar,
  - manual typed input in sidebar user filter.
- Ticker mention analytics panel now renders on all non-admin routes, using the currently loaded tweet set to visualize top mentioned symbols, mention share, chart-signal density, and quick insight tags.
- Ticker mention analytics are route-aware and user-aware: changing route scope or applying a user filter updates the visualization to that exact subset (for example, "what @user mentions most").
- Route-level segmentation pages implemented:
  - `/` home overview,
  - `/crypto` crypto widgets,
  - `/stocks` stock widgets,
  - `/forex` macro/forex widgets,
  - `/portfolio` portfolio management.
- Crypto and stock routes support chart-focused tweet ordering:
  - Latest,
  - Charts first,
  - Charts only.
- Tweet cards display a small "Chart" badge only when backend chart classification marks `has_chart=true`.
- Tweet cards display separate sentiment badges for the main post and quoted post using backend metadata.
- Portfolio route includes add/list/toggle/delete workflows and summary cards (positions, market value, cost basis, unrealized PnL).
- Home route includes a WallStreetBets radar widget with latest Reddit post momentum signals.
- Stocks route now includes a market-hours banner showing major exchange session state (open/pre-market/after-hours/closed) with explicit holiday closure labels when applicable.
- Crypto route now includes a Binance movers widget (top gainers/losers).
- Stocks route now includes a Nasdaq trading halts widget.
- Options route now includes a market activity widget for calls, puts, put/call ratio, and most-active contracts.
- Options route timeline now filters to tweets classified as options-intent (`is_options_tweet=true`) instead of generic stock-linked tweets.
- Options route now consumes options-only REST/SSE feeds so only options-classified tweets are fetched and rendered there.
- Forex route now includes an economic events widget backed by Investing high-impact calendar data.
- Forex route now includes a TradingView macro snapshot widget with yield curves and FX indices.
- Forex route now includes legacy crypto indices plus the stock/forex TradingView index panel.
- Economic events widget now displays country/region flag emojis and explicit impact badges per event.

## Connected End-to-End Today

- Tweet stream data: `/api/posts` + `/api/stream` -> timeline cards, filters, and sentiment badges.
- Fear & Greed widget: `/api/fear-greed` -> `FearGreedWidget`.
- Treemap widget: `/api/treemap` -> `TreemapWidget`.
- Trending crypto widget: `/api/trending-crypto` -> `TrendingCryptoWidget`.
- StockTwits widget: `/api/stocktwits` -> `StocktwitsWidget`.
- SPY heatmap widget: `/api/spy-heatmap` -> `SpyHeatmapWidget`.
- Binance movers widget: `/api/binance/gainers-losers` -> `BinanceGainersLosersWidget`.
- Nasdaq stock halts widget: `/api/stock-halts` -> `StockHaltsWidget`.
- Options overview widget: `/api/options/overview` -> `OptionsOverviewWidget`.
- Options tweet intent metadata: `/api/posts` + `/api/stream` -> options route timeline filtering (`is_options_tweet`, `options_context`).
- Market overview stream assets: `/api/posts` + `/api/stream` -> `MarketOverview`.
- TradingView TA summaries: `/api/posts` + `/api/stream` -> `tweet.assets[*].financials.technical_analysis` -> `TweetCard` / `AssetBadge`.
- Asset fundamentals: `/api/posts` + `/api/stream` -> `tweet.assets[*].fundamentals` -> `AssetFundamentals` in `TweetCard` / `AssetBadge`.
- Ticker mention pulse: `/api/posts` + `/api/stream` -> `TickerMentionsPanel` (route-scoped + user-scoped mention analytics).
- Debug admin panel: `/api/debug/tweet` -> `DebugAdminPanel` (`/admin`).
- Portfolio panel: `/api/portfolio/positions` + `/api/portfolio/summary` -> `PortfolioPanel` (`/portfolio`).
- WallStreetBets panel: `/api/reddit/wsb` -> `RedditWsbWidget` (`/`).
- Stock market-hours banner: `/api/stocks/market-hours` -> `StockMarketHoursBanner` (`/stocks`).
- Economic events panel: `/api/events/economic` -> `EconomicEventsWidget` (`/forex`).
- Macro snapshot panel: `/api/forex/macro` -> `ForexMacroWidget` (`/forex`).

## Backend APIs Not Yet Connected in Main UI

- No known unconnected backend API endpoints from the current `app/api/main.py` surface.

## Suggested Next Connections

- Continue legacy feature migration from `fintwit-bot` domains not yet ported (forex, options volume/SPACs/short-interest slices).
