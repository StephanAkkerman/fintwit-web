# API and Frontend Coverage Matrix

Last updated: 2026-09-01

## Authentication

- All endpoints under `/api/*` use the same API key dependency.
- If `API_KEY` is configured in backend env, clients must send `X-API-Key`.

## Endpoint Matrix

| Endpoint | Method | Data Source | Returns | Frontend Status |
| --- | --- | --- | --- | --- |
| `/api/posts` | GET | SQLite via `TweetRepo.latest` | Latest tweets including `assets`, engagement, media, symbols, full nested quoted tweet payload (`quoted_tweet`), and sentiment metadata for both main and quoted text (`sentiment_*`, `quoted_sentiment_*`). Supports pagination with `limit` (default 200, max 2000) and `before_id` for older pages. Also supports optional time-window filtering via `since_hours` (1-168). The frontend pages in fixed 200-item batches until the selected time window is exhausted, so the loaded set reflects the full window rather than an arbitrary cap. Tweet payload may include `is_subscriber_only` on top-level and quoted tweet objects when present from upstream. Options-intent metadata is also available as `is_options_tweet` + `options_context` when classification is positive. Supports `options_only=true` to return only options-classified tweets. Enriched `assets[*].financials` may also include `technical_analysis` with TradingView 4H/1D summaries for ticker widgets, `signa` with the Signa signal verdict for equity-like kinds, plus `last_close` for session-aware stock cards. | Connected via `useTweets` |
| `/api/stream` | GET (SSE) | In-memory broadcaster from stream worker | Real-time tweet/new engagement updates (including full `quoted_tweet` payload plus main + quoted sentiment metadata on new tweets). Stream payload may include `is_subscriber_only` on top-level and quoted tweet objects when present from upstream. Options-intent metadata is also included as `is_options_tweet` + `options_context` when classification is positive. Supports `options_only=true` to stream only options-classified tweets. Streamed `assets[*].financials` can also carry `technical_analysis` and `signa` for the same ticker widgets as REST-loaded tweets, plus `last_close` for pre-market/after-hours display. | Connected via `useTweets` |
| `/api/fear-greed` | GET | `alternative.me/fng` | `{ value, change, status }` | Connected via `FearGreedWidget` |
| `/api/treemap` | GET | `coin360.com/site-api/coins` | Coin360 top-100 treemap payload | Connected via `TreemapWidget` |
| `/api/trending-crypto` | GET | `coinmarketcap.com/data-api/v3/topsearch/rank` | List of trending coins with price/change/volume/website | Connected via `TrendingCryptoWidget` |
| `/api/signa/best-trades` | GET | `app.getsigna.ai/api/signals/run?scored=true` (undocumented public feed; no auth — tier-3 signals are gated server-side) | Ranked best-trade signals normalized per ticker: `direction`, `composite_score`, `grade`, `confidence`, `alert_tier`, `model_count`, `regime`, `categories`, `reason`, `key_drivers`, `generated_at`. Supports `limit` (1-250, default 100). | Connected via `useSignaBestTrades` / `SignaBestTradesWidget` (`/signa`, "Best Trades" tab) |
| `/api/signa/live-feed` | GET | `app.getsigna.ai/api/signals/feed` (undocumented public feed; no auth) | Raw, per-model live signals normalized per ticker, filtered to *directional* calls only (BUY/SELL/SHORT; AVOID/HOLD/WATCH dropped): `signal`, `direction`, `model_name`, `model_source`, `category`, `confidence`, `reason`, `entry_price`, `stop_level`, `target_price`, `position_size_pct`, `grade`, `tier`, `score`, `created_at`. Supports `limit` (1-15000, default 1500). | Connected via `useSignaLiveFeed` (polls every 5m) / `SignaLiveFeedWidget` (`/signa`, "Live Feed" tab) |
| `/api/binance/gainers-losers` | GET | `api.binance.com/api/v3/ticker/24hr` | Top USDT-pair gainers and losers with price, 24h change, volume, and Binance market URL | Connected via `BinanceGainersLosersWidget` |
| `/api/events/economic` | GET | `www.investing.com/economic-calendar/Service/getCalendarFilteredData` (high-impact, this-week view for US + Euro zone) | Economic calendar rows with date/time/zone/currency/event and actual/forecast/previous values plus impact metadata (`impact_score`, `impact_emoji`) | Connected via `EconomicEventsWidget` |
| `/api/forex/macro` | GET | TradingView quote fallback service (`app/services/tradingview_quote.py`) plus market-hours lookup (`app/services/market_hours_service.py`) over legacy macro symbols (`CRYPTOCAP:*`, `AMEX:SPY`, `NASDAQ:NDX`, `USI:PCC`, `USI:PCCE`, `TVC:VIX`, `TVC:SPX`, `TVC:DXY`, `TVC:EXY`, `TVC:BXY`, `TVC:JXY`, `TVC:US*Y`, `TVC:EU*Y`) | Macro snapshot payload with US/EU yield curve points, crypto indices, stock/forex indices, market-hours visibility, 2s10s spread, FX index quotes, and `as_of` timestamp | Connected via `ForexMacroWidget` |
| `/api/stocks/market-hours` | GET | `exchange_calendars` exchange sessions for representative global exchanges | Major exchange session status (`Open`, `Pre-market`, `After-hours`, `Closed`) with timezone plus closure metadata (`closure_reason`, `is_holiday`, optional `holiday_name`) when closed | Connected via `StockMarketHoursBanner` |
| `/api/stock-halts` | GET | `www.nasdaqtrader.com/RPCHandler.axd` (`BL_TradeHalt.GetTradeHalts`) | Current-day Nasdaq halt rows with halt time, issue symbol, and optional resumption time | Connected via `StockHaltsWidget` |
| `/api/options/overview` | GET | `api.nasdaq.com/api/quote/{symbol}/option-chain/most-active?assetclass=...` (aggregated across default major symbols, optional `symbols` query override) | Calls/puts totals, market put-call ratio, bullish-vs-bearish symbol ranking, and most-active contracts | Connected via `OptionsOverviewWidget` |
| `/api/stocktwits` | GET | `api.stocktwits.com/api/2/charts/{keyword}` (curl-first, then httpx; short-lived cache fallback on transient failures) | Formatted StockTwits rank list (`symbol`, `name`, `price`, `val`); returns `[]` during transient upstream unavailability | Connected via `StocktwitsWidget` |
| `/api/spy-heatmap` | GET | `phx.unusualwhales.com/api/etf/SPY/heatmap` | SPY heatmap JSON by date range | Connected via `SpyHeatmapWidget` |
| `/api/reddit/wsb` | GET | `asyncpraw` (credentials via env) with fallback to `reddit.com/r/{subreddit}/hot.json` via `httpx` | Recent non-stickied Reddit hot posts with title/body/media normalization | Connected via `RedditWsbWidget` |
| `/api/portfolio/positions` | GET | SQLite via `PortfolioRepo.list_positions` | Portfolio positions list | Connected via `usePortfolio` / `PortfolioPanel`; also via `usePortfolioTickers` (polls every 5m) to badge tweet-card tickers as Held / Recently Held |
| `/api/portfolio/positions` | POST | SQLite via `PortfolioRepo.create_position` | Created portfolio position | Connected via `usePortfolio` / `PortfolioPanel` |
| `/api/portfolio/positions/{position_id}` | PATCH | SQLite via `PortfolioRepo.update_position` | Updated portfolio position (active flag and editable fields) | Connected via `usePortfolio` / `PortfolioPanel` |
| `/api/portfolio/positions/{position_id}` | DELETE | SQLite via `PortfolioRepo.delete_position` | `{ ok: true }` on delete | Connected via `usePortfolio` / `PortfolioPanel` |
| `/api/portfolio/summary` | GET | SQLite positions + Yahoo Finance (`get_stock_info`) | Live valuation totals and per-position unrealized PnL | Connected via `usePortfolio` / `PortfolioPanel` |
| `/api/portfolio/history` | GET | Holdings from `IbkrRepo`/`PortfolioRepo` + Yahoo Finance chart history (`price_history_service`) + stored `portfolio_snapshots` | Portfolio value over time for a range (`1W`,`1M`,`3M`,`6M`,`YTD`,`1Y`,`5Y`,`MAX`; default `3M`). Points carry `value`, `cost_basis`, `pnl`, `pnl_percent` and a `source` of `snapshot` (recorded valuation), `reconstructed` (today's quantities priced at historical closes) or `live` (current quote). Also returns `holdings`, live `totals`, `start_value`/`end_value`/`change`/`change_percent`, and `missing_symbols` for holdings with no price history. `source=auto\|manual\|ibkr` selects the holdings set (`auto` prefers synced IBKR stock positions, else manually tracked ones). | Connected via `usePortfolioHistory` / `PortfolioValueChart` (`/portfolio`) |
| `/api/portfolio/insights` | GET | Holdings + Yahoo Finance quotes and full price history (`price_history_service.get_symbol_stats`) | Per-asset context: all-time high/low and 52-week high/low with dates, `from_ath_percent`/`from_atl_percent`, `range_position_52w`, `days_since_ath`/`days_since_atl`, plus ordered `flags` (`at_ath`, `near_ath`, `recent_ath`, `at_atl`, `near_atl`, `recent_atl`, `near_52w_high`, `near_52w_low`). Positions also carry live price, weight and unrealized PnL; `highlights` flattens the flags across holdings. Accepts the same `source` selector. | Connected via `usePortfolioInsights` / `PortfolioAssetInsights` (`/portfolio`) |
| `/api/debug/tweet` | POST | Internal debug helper + enrichment | Injected tweet payload persisted + broadcast, including options-intent classification fields (`is_options_tweet`, `options_context`) | Connected via `DebugAdminPanel` (`/admin`) |
| `/api/overview/mention-frequency` | POST | SQLite via `mention_aggregator.get_mention_frequency` (json_each over `tweets`) | Batch per-(author, ticker) mention-frequency stats over a 30d window in two scopes — `personal` (the tweet author) and `global` (all users). Body: `{ requests: [{ author, tickers[] }] }` (max 300 authors). Each `TickerScopeStat` carries `mentions`, `prev_mentions`, a primary `signal` (`new`/`resurfacing`/`top`/`hot`/`rising`/`falling`/`neutral`), `rank`, `pct_change`, `days_since_last`, sentiment `stance` (+`stance_flipped`), and a `notable` flag. | Connected via `useMentionFrequency` → `AssetMentions` inside each `TweetCard` asset card |

## Enrichment Data Flow (Indirect APIs)

These services are not exposed as standalone endpoints, but are used in asset enrichment for tweets:

- Yahoo Finance (`query1.finance.yahoo.com`) for equities:
  - returns `price`, `last_close`, `change_percent`, `volume`, `website`, `source`.
  - now uses short-lived cache/throttling and classifier-provided `yahoo_lookup` symbols (including centralized shortcut mappings for symbols like `SPY` and `DXY`) to reduce transient rate-limit misses for ETF/index/forex-like symbols.
  - if Yahoo is unavailable/rate-limited and no stale cache exists, uses TradingView symbol quote fallback.
- CoinGecko (`api.coingecko.com`) for crypto:
  - returns `price`, `change_percent`, `volume`, `website`, `source`.
  - uses short-lived cache and Yahoo `-USD` fallback when CoinGecko is rate-limited (`429`) or temporarily unavailable; if Yahoo fallback also fails, attempts TradingView quote fallback.
- FinTwitBERT sentiment (`StephanAkkerman/FinTwitBERT-sentiment`) for tweet text:
  - returns separate main-post and quoted-post sentiment fields (`sentiment_*`, `quoted_sentiment_*`).
  - historical tweets can be backfilled via `python -m app.runtime.backfill_sentiment`.

The enriched values are attached under `tweet.assets[*].financials` and consumed in `TweetCard`.
`tweet.assets[*].financials.source` indicates which provider served the quote (for example `yahoo`, `coingecko`, `tradingview`).
`tweet.assets[*].financials.last_close` carries the previous close for session-aware stock cards.
`tweet.assets[*].financials.technical_analysis` carries TradingView 4H/1D recommendation summaries for ticker widgets.
`tweet.assets[*].financials.signa` carries the Signa signal verdict (`signal`, `score`, `trend`, `confidence`, `timeframe`) for equity-like kinds only (`EQUITY`, `ETF`, `INDEX`, `FUTURE`); the verdict is color-coded green/red/grey by direction in the UI.
Static classification metadata under `tweet.assets[*]` may also include `sector` and `industry` for equities.
`tweet.assets[*].fundamentals` carries slow-moving valuation/volume metrics read from the same Yahoo quote `ticker-classifier` uses to classify the symbol, so it costs no extra requests: `market_cap`, `forward_pe`, `trailing_pe`, `eps_forward`, `eps_trailing`, `avg_volume` (3-month daily average, in shares), `avg_volume_10d`, and `currency`. Only the fields Yahoo actually reported are present -- a missing field means unknown, never zero -- and non-positive ratios/volumes are dropped rather than rendered as `0`. Crypto assets carry a `market_cap` alone (from CoinGecko); indices, futures and forex pairs generally carry no fundamentals at all.
Ambiguous symbols are disambiguated in enrichment with local overrides before cache/classifier fallback (for example `ETH` is forced to crypto, and `EURUSD`/`USOIL` map to Yahoo-compatible lookups).
Unsupported classifier kinds (for example `UNKNOWN`) are excluded from `tweet.assets` so topic hashtags are less likely to appear as false asset cards.
Asset enrichment is driven by cashtags/tickers; hashtags are still returned in tweet metadata but are not promoted to asset cards by themselves.
For equities/ETFs, `tweet.assets[*].company_profile` may include curated financedatabase fields: `industry_group`, `country`, `exchange`, `currency`, `website`, and `market_cap_category`.

## Frontend Contract Notes

- Route-level sections are path-based and mounted in `App.tsx`:
  - `/` home overview,
  - `/crypto` crypto-focused widgets,
  - `/stocks` stock-focused widgets,
  - `/forex` macro/forex-focused widgets,
  - `/options` options market-activity widgets,
  - `/portfolio` portfolio overview (value-over-time chart, per-asset ATH/ATL context, live IBKR positions) and portfolio management.

- Primary contracts live in `frontend/src/types.ts` (tweets, market widgets, and portfolio types, including `PortfolioHistory`, `PortfolioHistoryPoint`, `PortfolioInsights`, `PortfolioInsightPosition`, `PortfolioAssetStats`, and `PortfolioAssetFlag`).
- Containerized frontend proxy wiring: Nginx now resolves backend service DNS dynamically (`resolver 127.0.0.11`) on port 7999 for `/api/*` and `/api/stream` upstream routes to avoid stale upstream IPs after backend container restarts.
- Timeline and filters rely on:
  - `tickers`, `hashtags`, and symbol extraction from text,
  - route-level section selection for category scope (home/all, crypto, stock/macro, options-only feed),
  - `assets[].symbol` and `assets[].kind` for ticker and route-scoped filtering,
  - `user_name` and `user_screen_name` for user-based filtering from sidebar input and author click actions,
  - `is_subscriber_only` for the sidebar subscriber-only filter and exclusivity badges,
  - `assets[].fundamentals` plus `assets[].sector`/`assets[].industry` for the `AssetFundamentals` strip shown by default in `TweetCard` and `AssetBadge` (market cap, forward P/E falling back to trailing P/E, 3-month average volume, and the industry with the sector kept in its tooltip), with the P/E colour-coded green/grey/red by valuation band via `scoreMetric`/`metricQualityTextClass` (`utils/metricQuality`), a generic three-band numeric scale reusable for other metrics,
  - `assets[].financials.technical_analysis` for TradingView 4H/1D summary rows in `TweetCard` and `AssetBadge` (recommendation color-coded by direction via `directionColor`),
  - `assets[].financials.signa` for the Signa signal row in `TweetCard` and `AssetBadge` (verdict color-coded green/red/grey via `directionColor`),
  - `assets[].financials.website` for price links,
  - `assets[].financials.last_close` for last-close context in pre-market/after-hours cards,
  - `assets[].symbol`, `assets[].name`, `assets[].kind`, `assets[].financials.price`, `assets[].financials.last_close`, and `assets[].financials.change_percent` for compact financial card rendering in `TweetCard`,
  - `title` + `quoted_tweet` to distinguish reposts from quote embeds and render original-author header with reposter attribution,
  - `is_subscriber_only` for native-style subscriber-only icons in main tweet headers and quote headers,
  - `is_options_tweet` and `options_context` for options-intent route filtering and structured options tweet metadata,
  - tweet `text` is rendered with preserved user-authored line breaks and blank lines,
  - `sentiment_*` for main-post sentiment rendering,
  - `quoted_sentiment_*` for quote-post sentiment rendering.
  - media URLs are rendered as in-page image previews (lightbox) in `TweetCard` rather than opening directly in a new tab on image click.
  - `created_at` is serialized with explicit UTC offset and rendered in the viewer's local timezone in `TweetCard`.
  - quote embeds in `TweetCard` display quoted author identity and quoted timestamp in the embed header (using API-provided quote fields when available, with markdown/URL inference fallback).
  - quote embeds in `TweetCard` also render the quoted user's avatar in the header (from `quoted_tweet.user_img` or `quoted_user_img` fallback).
  - when present, quote embeds prefer `quoted_tweet` metadata/media from backend over markdown parsing heuristics.
  - `TickerMentionsPanel` derives "top mentioned symbols" analytics from the loaded timeline subset (post route scope + user filter + portfolio/options constraints) and supports click-through ticker filtering from its bars.
  - `useTweets` now requests `/api/posts` with `since_hours=24` by default, so timeline and analytics are anchored to the last 24h of loaded tweets.
  - Sidebar lookback controls can switch `since_hours` between `24`, `48`, and `168` to compare response/load behavior while keeping route/user filters intact.
  - `useTweets` exposes load-impact stats (`lastLoadDurationMs`, `lastLoadedCount`, `tweets.length`) that are surfaced in the sidebar for quick performance comparison across windows.
  - `useMentionFrequency` derives `{ author, tickers }` from the displayed tweets, batches them into one `POST /api/overview/mention-frequency`, caches per `author|ticker` with a 5-minute TTL, and feeds a `lookup` into each `TweetCard`. `AssetMentions` renders inside each resolved asset card (next to price/TA/Signa) and only when that ticker's personal or global stat is `notable`: an `@<author>` line and an `all` line, each with a signal emoji (`🆕`/`🥇`/`🔥`/`📈`/`📉`), a stance emoji (`🐂`/`🐻`/`🔀`), a 30d count, an inline trend `%`, and a detail tooltip. Tickers without a resolved asset card show no mention stats.

- Crypto route widgets rely on:
  - `/api/trending-crypto` for top searched coin context,
  - `/api/binance/gainers-losers` for short-horizon momentum lists (top gainers/losers).

- Stocks route widgets rely on:
  - `/api/stocks/market-hours` for exchange session state,
  - `/api/stock-halts` for same-day halt/resumption activity,
  - `/api/stocktwits` and `/api/spy-heatmap` for social and market breadth context.

- Options route widgets rely on:
  - `/api/options/overview` for aggregated calls/puts totals, put-call ratio, and most-active option contracts.
