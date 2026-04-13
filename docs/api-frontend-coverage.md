# API and Frontend Coverage Matrix

Last updated: 2026-04-13

## Authentication

- All endpoints under `/api/*` use the same API key dependency.
- If `API_KEY` is configured in backend env, clients must send `X-API-Key`.

## Endpoint Matrix

| Endpoint | Method | Data Source | Returns | Frontend Status |
| --- | --- | --- | --- | --- |
| `/api/posts` | GET | SQLite via `TweetRepo.latest` | Latest tweets including `assets`, engagement, media, symbols, full nested quoted tweet payload (`quoted_tweet`), and sentiment metadata for both main and quoted text (`sentiment_*`, `quoted_sentiment_*`). Supports pagination with `limit` (default 200, max 200) and `before_id` for older pages. Tweet payload may include `is_subscriber_only` on top-level and quoted tweet objects when present from upstream. Options-intent metadata is also available as `is_options_tweet` + `options_context` when classification is positive. Supports `options_only=true` to return only options-classified tweets. | Connected via `useTweets` |
| `/api/stream` | GET (SSE) | In-memory broadcaster from stream worker | Real-time tweet/new engagement updates (including full `quoted_tweet` payload plus main + quoted sentiment metadata on new tweets). Stream payload may include `is_subscriber_only` on top-level and quoted tweet objects when present from upstream. Options-intent metadata is also included as `is_options_tweet` + `options_context` when classification is positive. Supports `options_only=true` to stream only options-classified tweets. | Connected via `useTweets` |
| `/api/fear-greed` | GET | `alternative.me/fng` | `{ value, change, status }` | Connected via `FearGreedWidget` |
| `/api/treemap` | GET | `coin360.com/site-api/coins` | Coin360 top-100 treemap payload | Connected via `TreemapWidget` |
| `/api/trending-crypto` | GET | `coinmarketcap.com/data-api/v3/topsearch/rank` | List of trending coins with price/change/volume/website | Connected via `TrendingCryptoWidget` |
| `/api/binance/gainers-losers` | GET | `api.binance.com/api/v3/ticker/24hr` | Top USDT-pair gainers and losers with price, 24h change, volume, and Binance market URL | Connected via `BinanceGainersLosersWidget` |
| `/api/events/economic` | GET | `www.investing.com/economic-calendar/Service/getCalendarFilteredData` (high-impact, this-week view for US + Euro zone) | Economic calendar rows with date/time/zone/currency/event and actual/forecast/previous values plus impact metadata (`impact_score`, `impact_emoji`) | Connected via `EconomicEventsWidget` |
| `/api/nfts/trending` | GET | `api.coingecko.com/api/v3/search/trending` (`nfts` section) | Trending NFT collections with floor price, floor currency, floor 24h change, thumbnail, and website | Connected via `NftTrendingWidget` |
| `/api/stocks/market-hours` | GET | `query1.finance.yahoo.com/v7/finance/quote` market-state fields for representative exchange symbols (short-lived cache + stale-cache fallback on transient failures/rate limits) | Major exchange session status (`Open`, `Pre-market`, `After-hours`, `Closed`) with timezone and exchange metadata | Connected via `StockMarketHoursBanner` |
| `/api/stock-halts` | GET | `www.nasdaqtrader.com/RPCHandler.axd` (`BL_TradeHalt.GetTradeHalts`) | Current-day Nasdaq halt rows with halt time, issue symbol, and optional resumption time | Connected via `StockHaltsWidget` |
| `/api/options/overview` | GET | `api.nasdaq.com/api/quote/{symbol}/option-chain/most-active?assetclass=...` (aggregated across default major symbols, optional `symbols` query override) | Calls/puts totals, market put-call ratio, bullish-vs-bearish symbol ranking, and most-active contracts | Connected via `OptionsOverviewWidget` |
| `/api/stocktwits` | GET | `api.stocktwits.com/api/2/charts/{keyword}` (curl-first, then httpx; short-lived cache fallback on transient failures) | Formatted StockTwits rank list (`symbol`, `name`, `price`, `val`); returns `[]` during transient upstream unavailability | Connected via `StocktwitsWidget` |
| `/api/spy-heatmap` | GET | `phx.unusualwhales.com/api/etf/SPY/heatmap` | SPY heatmap JSON by date range | Connected via `SpyHeatmapWidget` |
| `/api/reddit/wsb` | GET | `asyncpraw` (credentials via env) with fallback to `reddit.com/r/{subreddit}/hot.json` via `httpx` | Recent non-stickied Reddit hot posts with title/body/media normalization | Connected via `RedditWsbWidget` |
| `/api/portfolio/positions` | GET | SQLite via `PortfolioRepo.list_positions` | Portfolio positions list | Connected via `usePortfolio` / `PortfolioPanel` |
| `/api/portfolio/positions` | POST | SQLite via `PortfolioRepo.create_position` | Created portfolio position | Connected via `usePortfolio` / `PortfolioPanel` |
| `/api/portfolio/positions/{position_id}` | PATCH | SQLite via `PortfolioRepo.update_position` | Updated portfolio position (active flag and editable fields) | Connected via `usePortfolio` / `PortfolioPanel` |
| `/api/portfolio/positions/{position_id}` | DELETE | SQLite via `PortfolioRepo.delete_position` | `{ ok: true }` on delete | Connected via `usePortfolio` / `PortfolioPanel` |
| `/api/portfolio/summary` | GET | SQLite positions + Yahoo Finance (`get_stock_info`) | Live valuation totals and per-position unrealized PnL | Connected via `usePortfolio` / `PortfolioPanel` |
| `/api/debug/tweet` | POST | Internal debug helper + enrichment | Injected tweet payload persisted + broadcast, including options-intent classification fields (`is_options_tweet`, `options_context`) | Connected via `DebugAdminPanel` (`/admin`) |

## Enrichment Data Flow (Indirect APIs)

These services are not exposed as standalone endpoints, but are used in asset enrichment for tweets:

- Yahoo Finance (`query1.finance.yahoo.com`) for equities:
  - returns `price`, `change_percent`, `volume`, `website`, `source`.
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
Static classification metadata under `tweet.assets[*]` may also include `sector` and `industry` for equities.
Ambiguous symbols are disambiguated in enrichment with local overrides before cache/classifier fallback (for example `ETH` is forced to crypto, and `EURUSD`/`USOIL` map to Yahoo-compatible lookups).
For equities/ETFs, `tweet.assets[*].company_profile` may include curated financedatabase fields: `industry_group`, `country`, `exchange`, `currency`, `website`, and `market_cap_category`.

## Frontend Contract Notes

- Route-level sections are path-based and mounted in `App.tsx`:
  - `/` home overview,
  - `/crypto` crypto-focused widgets,
  - `/stocks` stock-focused widgets,
  - `/forex` macro/forex-focused widgets,
  - `/options` options market-activity widgets,
  - `/nfts` NFT-focused widgets,
  - `/portfolio` portfolio management.

- Primary contracts live in `frontend/src/types.ts` (tweets, market widgets, and portfolio types).
- Timeline and filters rely on:
  - `tickers`, `hashtags`, and symbol extraction from text,
  - route-level section selection for category scope (home/all, crypto, stock/macro, options-only feed),
  - `assets[].symbol` and `assets[].kind` for ticker and route-scoped filtering,
  - `assets[].financials.website` for price links,
  - `assets[].symbol`, `assets[].name`, `assets[].kind`, `assets[].financials.price`, and `assets[].financials.change_percent` for compact financial card rendering in `TweetCard`,
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

- Crypto route widgets rely on:
  - `/api/trending-crypto` for top searched coin context,
  - `/api/binance/gainers-losers` for short-horizon momentum lists (top gainers/losers).

- Stocks route widgets rely on:
  - `/api/stocks/market-hours` for exchange session state,
  - `/api/stock-halts` for same-day halt/resumption activity,
  - `/api/stocktwits` and `/api/spy-heatmap` for social and market breadth context.

- Options route widgets rely on:
  - `/api/options/overview` for aggregated calls/puts totals, put-call ratio, and most-active option contracts.
