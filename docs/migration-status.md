# Migration Status

Last updated: 2026-09-03

## Backend: Implemented

- StockTwits community sentiment (Bullish/Bearish split) is now attached to enriched tweet asset financial payloads under `stocktwits_sentiment`, sourced from `api-gw-prd.stocktwits.com/sentiment-api/v2/{symbol}/detail` (curl-first, httpx fallback, short-lived per-symbol cache -- same anti-bot strategy as the existing `/api/stocktwits` rankings). Fetched for every supported kind (stocks and crypto alike), unlike the equity-only Signa signal. The upstream schema is undocumented, so `get_stocktwits_sentiment()` parses defensively across a few plausible field-name/shape variants and returns `None` rather than guessing when nothing recognizable is found.
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
- Stock migration slice: stock market Fear & Greed endpoint (`/api/stocks/fear-greed`) now available, sourced from feargreedmeter.com's undocumented `api2.mmeter.app/data/summary` backend. The response shape is not publicly documented, so `stock_fear_greed_service.py` tolerates a few plausible shapes and returns `503` when none match, with a short-lived cache so a transient upstream failure can still serve the last known reading.
- Stock market-hours endpoint now derives schedules from `exchange_calendars` and includes explicit closed-session context (`closure_reason`, `is_holiday`, optional `holiday_name`) so holiday closures can be distinguished from weekends.
- Events migration slice: Investing economic calendar endpoint (`/api/events/economic`) now available for high-impact US and Euro-zone events.
- Forex/macro migration slice: TradingView-backed macro snapshot endpoint (`/api/forex/macro`) now exposes US/EU yield curves plus major FX index quotes for the `/forex` route.
- Forex/macro migration slice: the macro snapshot now also includes legacy crypto indices and the stock/forex TradingView index panel, with market-hours-aware visibility for the legacy stock/forex block.
- Service-backed endpoints for Fear & Greed, treemap, StockTwits, SPY heatmap, trending crypto, and WallStreetBets Reddit hot posts.
- Stock migration slice: sector/subsector market overview endpoint (`/api/spy-heatmap/sectors`, `app/services/unusual_whales.py:summarize_spy_sectors`) groups the SPY heatmap universe by GICS sector and, within each sector, by `industry` (subsector, e.g. "Semiconductors" inside "Technology") — a plain sector is too coarse to see a narrow move. Each level reports a market-cap-weighted average `change_percent`, total `market_cap`, and `stock_count`.
- Reddit WallStreetBets ingestion uses asyncpraw-first (legacy-style credentials) with HTTP JSON fallback when credentials are missing.
- StockTwits service fallback for anti-bot blocks: curl-first fetch strategy with short-lived per-keyword cache fallback to avoid transient 503s (curl is executed via thread-backed sync subprocess for Windows/uvicorn compatibility).
- Portfolio backend for IBKR-style stock tracking: positions CRUD endpoints and live summary valuation/PnL using Yahoo quotes.
- Portfolio overview slice: `app/services/price_history_service.py` (cached Yahoo chart history plus ATH/ATL and 52-week statistics), `app/runtime/portfolio_valuation.py` (holdings resolution, live valuation, value-over-time reconstruction, per-asset insights, sector grouping and concentration scoring), `portfolio_snapshots` table + `PortfolioRepo` snapshot CRUD, and the `app/runtime/portfolio_snapshot.py` worker started from lifespan (interval via `PORTFOLIO_SNAPSHOT_INTERVAL`, default 1800s). Exposed as `GET /api/portfolio/history` and `GET /api/portfolio/insights`; both accept `source=auto|manual|ibkr`, where `auto` prefers synced IBKR stock positions and falls back to manually tracked ones.
- Portfolio balance/sector insights: `app/runtime/portfolio_valuation.py:build_diversification` classifies each holding via `ticker_classifier` (GICS sector for equities/ETFs, asset category otherwise), groups holdings into sectors, and scores concentration with a Herfindahl-Hirschman index at both the holding and sector level. Folded into `GET /api/portfolio/insights` as `sectors` and `diversification`.
- Deployment scaffolding for self-hosting: backend Docker image, frontend Nginx reverse proxy for `/api/*` + `/api/stream`, Docker Compose stack for Raspberry Pi, and Terraform-managed Cloudflare tunnel + DNS.
- Frontend proxy resilience hardening: containerized Nginx now uses Docker DNS re-resolution for backend upstream (`backend:7999`) so backend restarts do not leave stale upstream IPs that can surface first-hit `502` responses.
- Chart data extraction (issue #49): when `chart-recognizer` classifies a tweet's image as a chart (`has_chart=true`) and the tweet text mentions no ticker, `app/ml/chart_extractor.py` (wrapping the external [`chart-extractor`](https://github.com/StephanAkkerman/chart-extractor) YOLO+OCR package) analyzes the image and attaches a `chart_extraction` payload (`symbol`, `exchange`, `timeframe`, `price`, `session`) to the tweet. Skipped entirely when the text already names a ticker, since the mentioned ticker is a stronger, cheaper signal than OCR. Runs lazily/thread-offloaded like `chart-recognizer`, and can be disabled independently via `CHART_EXTRACTION_ENABLED=false`.

- Sector/industry mention overview (issue #104): `mention_aggregator.get_sector_mentions` aggregates ticker mentions from `tweets.assets[*].sector`/`.industry` (equities/ETFs only — crypto and forex carry no sector metadata and are excluded) into a sector -> industry -> ticker rollup, so a cluster of activity across several related tickers (e.g. "Technology > Semiconductors") surfaces as a sector-level trend. Ranking uses the same fairness-adjusted `mention_score` as `get_mention_heat` (issue #101), capping each author's contribution per sector at `AUTHOR_MENTION_CAP`. Exposed via `GET /api/overview/sector-mentions` (`window_hours`, `limit`, plus the standard `user_screen_name`/`subscriber_only` filters).
- Home dashboard analytics slice (issue #101): `mention_aggregator.get_mention_heat` ranks the top-mentioned tickers over `window_hours` using a fairness-adjusted `mention_score` (each author's contribution capped at `AUTHOR_MENTION_CAP` before summing, so one spamming account can't out-rank a ticker genuinely spread across several authors) plus a point-to-point `price_direction` return over the window. Exposed via `GET /api/overview/mention-heat` (`asset_kind`, `window_hours`, `user_screen_name`, `subscriber_only`).
- Sentiment-shift ranking: `mention_aggregator.get_sentiment_shift` ranks tickers by absolute change in average FinTwitBERT sentiment between the active window and the prior baseline span (everything before the window cutoff, out to `max(window_hours * 2, 7d)`), surfacing tickers whose tweet sentiment is swinging fastest rather than just the loudest. Exposed via `GET /api/overview/sentiment-shift`.
- Mention-volume anomaly detection: `mention_aggregator.get_volume_baseline` flags tickers whose mention count in the active window exceeds `threshold` (default 1.5x) times their expected count from a rolling baseline (4x the active window, floored at 7 days), i.e. tickers suddenly getting talked about far more than usual. Exposed via `GET /api/overview/volume-baseline`.
- Hidden-gem detection: `mention_aggregator.get_hidden_gems` surfaces tickers that are newly appearing or resurfacing (no mention in at least `max(window_hours * 7, 7d)` prior) in the active window, using the same fairness-adjusted `mention_score` as `get_mention_heat` but with no minimum-mentions floor, since a single early mention is the point. Exposed via `GET /api/overview/hidden-gems`.
- Macro strip: `GET /api/overview/macro-strip` returns live TradingView quotes (price + % change) for a fixed watchlist (SPX, NDX, BTC, ETH, DXY, VIX, GOLD), 5-minute server-side cached.

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
- Financial asset blocks in tweet cards are intentionally compact and now show ticker, full name, type, current price, last close when available, daily % change, optional TradingView TA summary rows, and an optional StockTwits Bullish/Bearish sentiment row (`StocktwitsSentiment`, also shared by `AssetBadge`).
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
- Tweet cards display a "🔎 SYMBOL · TIMEFRAME · PRICE" badge when the backend attaches `chart_extraction` (chart data OCR'd off the image for tickerless chart tweets — issue #49).
- Tweet cards display separate sentiment badges for the main post and quoted post using backend metadata.
- Tweet card financial asset blocks display a portfolio-status badge (💼 Held / 🕓 Recently Held) when the ticker matches a current or recently-closed (within 30 days) portfolio position.
- Portfolio route includes add/list/toggle/delete workflows and summary cards (positions, market value, cost basis, unrealized PnL).
- Portfolio route now leads with a value-over-time area chart (`PortfolioValueChart`, Recharts) with selectable ranges (1W-MAX), a cost-basis reference line, hover tooltip, and a table view so no value is hover-only.
- Portfolio route also shows per-asset context (`PortfolioAssetInsights`): distance from all-time high/low, 52-week range position, and highlight badges for assets at/near — or recently at — an ATH or ATL.
- Portfolio route now shows sector allocation and a balance score (`PortfolioDiversification`): a sector-by-sector weight breakdown with constituent symbols, a diversification label (unrated/concentrated/moderate/diversified), and the largest holding/sector.
- Home route includes a WallStreetBets radar widget with latest Reddit post momentum signals.
- Stocks route now includes a market-hours banner showing major exchange session state (open/pre-market/after-hours/closed) with explicit holiday closure labels when applicable.
- Crypto route now includes a Binance movers widget (top gainers/losers).
- Stocks route now includes a Nasdaq trading halts widget.
- Stocks route now includes a stock market Fear & Greed index card.
- Options route now includes a market activity widget for calls, puts, put/call ratio, and most-active contracts.
- Options route timeline now filters to tweets classified as options-intent (`is_options_tweet=true`) instead of generic stock-linked tweets.
- Options route now consumes options-only REST/SSE feeds so only options-classified tweets are fetched and rendered there.
- Forex route now includes an economic events widget backed by Investing high-impact calendar data.
- Forex route now includes a TradingView macro snapshot widget with yield curves and FX indices.
- Forex route now includes legacy crypto indices plus the stock/forex TradingView index panel.
- Economic events widget now displays country/region flag emojis and explicit impact badges per event.
- Clicking any ticker (tweet cards, ticker mention pulse, mention heatmap) now opens a `TickerDetailModal` with a mentions-over-time chart, a bullish/bearish/neutral sentiment breakdown chart, and summary stats (total mentions, avg mentions per bucket, unique voices, chart-tagged tweets, avg engagement, price move, asset kind) for a selectable 24h/7d/30d window — resolves issue #108.
- Home route overview dashboard now includes a "Sectors & industries" widget (`SectorMentionsWidget`, issue #104): sectors ranked by mention volume with a proportional bar, top mentioned tickers per sector, and an expandable industry breakdown (e.g. "Technology > Semiconductors") — surfaces which corner of the market is getting talked about most, ahead of any single ticker breaking out.
- Home route overview dashboard (`OverviewDashboard`, mounted at `/`) leads with a macro strip (`MacroStrip`) showing live SPX/NDX/BTC/ETH/DXY/VIX/GOLD quotes with sparklines, then the mention-heat heatmap, then a three-column analytics row: `SentimentShiftWidget` (tickers with the biggest sentiment swing between now and the prior baseline), `VolumeBaselineWidget` ("Unusually loud" — tickers whose mention volume is a multiple of their rolling baseline), and `HiddenGemWidget` (newly-appearing or resurfacing tickers, tagged ✦ new / ↩ resurface).

## Connected End-to-End Today

- Tweet stream data: `/api/posts` + `/api/stream` -> timeline cards, filters, and sentiment badges.
- Fear & Greed widget: `/api/fear-greed` -> `FearGreedWidget`.
- Stock Fear & Greed widget: `/api/stocks/fear-greed` -> `StockFearGreedWidget` (`/stocks`).
- Treemap widget: `/api/treemap` -> `TreemapWidget`.
- Trending crypto widget: `/api/trending-crypto` -> `TrendingCryptoWidget`.
- StockTwits widget: `/api/stocktwits` -> `StocktwitsWidget`.
- SPY heatmap widget: `/api/spy-heatmap` -> `SpyHeatmapWidget`.
- Sector overview widget: `/api/spy-heatmap/sectors` -> `useSectorOverview` -> `SectorOverviewWidget` (`/stocks`).
- Binance movers widget: `/api/binance/gainers-losers` -> `BinanceGainersLosersWidget`.
- Nasdaq stock halts widget: `/api/stock-halts` -> `StockHaltsWidget`.
- Options overview widget: `/api/options/overview` -> `OptionsOverviewWidget`.
- Options tweet intent metadata: `/api/posts` + `/api/stream` -> options route timeline filtering (`is_options_tweet`, `options_context`).
- Market overview stream assets: `/api/posts` + `/api/stream` -> `MarketOverview`.
- TradingView TA summaries: `/api/posts` + `/api/stream` -> `tweet.assets[*].financials.technical_analysis` -> `TweetCard` / `AssetBadge`.
- Asset fundamentals: `/api/posts` + `/api/stream` -> `tweet.assets[*].fundamentals` -> `AssetFundamentals` in `TweetCard` / `AssetBadge`.
- Route-scoped mention heat: `/api/overview/mention-heat` -> `MentionHeatmap` (route-scoped `assetKind` + user-scoped mention/sentiment/price analytics; shown on `/crypto`, `/stocks`, `/forex`, `/options`, `/portfolio`, and on `/` via `OverviewDashboard`). Replaced the old client-computed `TickerMentionsPanel` (issue #94).
- Macro strip: `/api/overview/macro-strip` -> `MacroStrip` (`/` via `OverviewDashboard`).
- Sentiment-shift ranking: `/api/overview/sentiment-shift` -> `useSentimentShift` -> `SentimentShiftWidget` (`/` via `OverviewDashboard`).
- Mention-volume anomaly detection: `/api/overview/volume-baseline` -> `useVolumeBaseline` -> `VolumeBaselineWidget` (`/` via `OverviewDashboard`).
- Hidden-gem detection: `/api/overview/hidden-gems` -> `useHiddenGems` -> `HiddenGemWidget` (`/` via `OverviewDashboard`).
- Sector/industry mentions: `/api/overview/sector-mentions` -> `useSectorMentions` -> `SectorMentionsWidget` (shown on `/` via `OverviewDashboard`, below the mention-heat/sentiment/volume/hidden-gem row; expand a sector for its industry breakdown, click a ticker chip to apply the sidebar ticker filter) (issue #104).
- Ticker detail modal: `/api/overview/ticker-timeseries` -> `useTickerTimeseries` -> `TickerDetailModal` (mentions-over-time chart, bullish/bearish sentiment breakdown, and summary stats; opened by clicking any ticker across `TweetCard`, `MentionHeatmap`).
- Debug admin panel: `/api/debug/tweet` -> `DebugAdminPanel` (`/admin`).
- Portfolio panel: `/api/portfolio/positions` + `/api/portfolio/summary` -> `PortfolioPanel` (`/portfolio`).
- Portfolio ticker badges: `/api/portfolio/positions` -> `usePortfolioTickers` -> `TweetCard` financial asset blocks (all routes).
- Portfolio value chart: `/api/portfolio/history` -> `usePortfolioHistory` -> `PortfolioValueChart` (`/portfolio`).
- Portfolio asset context: `/api/portfolio/insights` -> `usePortfolioInsights` -> `PortfolioAssetInsights` (`/portfolio`).
- Portfolio balance/sectors: `/api/portfolio/insights` -> `usePortfolioInsights` -> `PortfolioDiversification` (`/portfolio`).
- WallStreetBets panel: `/api/reddit/wsb` -> `RedditWsbWidget` (`/`).
- Stock market-hours banner: `/api/stocks/market-hours` -> `StockMarketHoursBanner` (`/stocks`).
- Economic events panel: `/api/events/economic` -> `EconomicEventsWidget` (`/forex`).
- Macro snapshot panel: `/api/forex/macro` -> `ForexMacroWidget` (`/forex`).

## Backend APIs Not Yet Connected in Main UI

- No known unconnected backend API endpoints from the current `app/api/main.py` surface.

## Suggested Next Connections

- Continue legacy feature migration from `fintwit-bot` domains not yet ported (forex, options volume/SPACs/short-interest slices).
