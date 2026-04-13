# Migration Status

Last updated: 2026-04-13

## Backend: Implemented

- FastAPI app lifecycle with DB init and background tweet stream worker.
- API key dependency (`X-API-Key`) on all `/api/*` endpoints when `API_KEY` env var is set.
- Tweet ingestion and persistence from X timeline (`xclient`) with idempotent upsert.
- Symbol extraction fallback from tweet text (`$TICKER`, `#HASHTAG`) and symbol merge logic.
- Asset enrichment via `ticker-classifier` + Yahoo (equities) + CoinGecko (crypto).
- Asset enrichment hardening: uses classifier `yahoo_lookup` with centralized shortcut mappings in `ticker-classifier` (e.g. `DXY` -> `DX-Y.NYB`) so ETF/index/forex-style symbols are more reliably priced/classified.
- Asset enrichment local symbol overrides: ambiguous symbols now use deterministic mappings before pricing/classification (`ETH` forced to `CRYPTO`; `EURUSD` -> `EURUSD=X`; `USOIL` -> `CL=F`).
- Quote fallback hardening: when Yahoo/CoinGecko are rate-limited or unavailable, enrichment now attempts TradingView quote fallback before returning no price data.
- Quote source marker: enriched financial payload now includes `source` so frontend can display the provider used (`yahoo`, `coingecko`, `tradingview`).
- Equity asset enrichment now includes optional `sector` and `industry` metadata (for example `AAPL`/`NVDA` tagged as technology) sourced from classifier metadata.
- Equity/ETF asset enrichment now includes optional `company_profile` metadata (`industry_group`, `country`, `exchange`, `currency`, `website`, `market_cap_category`) from classifier metadata.
- Crypto enrichment hardening: CoinGecko caching and Yahoo `-USD` fallback when CoinGecko returns rate-limit/transient failures.
- FinTwitBERT sentiment classification for streamed tweets with separate main-post and quoted-post outputs (main: `sentiment_*`, quoted: `quoted_sentiment_*`).
- Full nested quoted tweet payload passthrough (`quoted_tweet`) from xtimeline is now persisted and served via `/api/posts`/`/api/stream`.
- Operational backfill command for historical tweet sentiment (`python -m app.runtime.backfill_sentiment`).
- SSE broadcasting (`/api/stream`) and engagement update handling for tweet updates.
- Service-backed endpoints for Fear & Greed, treemap, StockTwits, SPY heatmap, and trending crypto.
- Additional market-microstructure endpoints now available: Binance gainers/losers (`/api/binance/gainers-losers`) and Nasdaq stock halts (`/api/stock-halts`).
- Options migration slice: market options overview endpoint (`/api/options/overview`) now available, powered by Nasdaq most-active option-chain data for major US underlyings.
- Stream/runtime options-intent classification now tags tweets with `is_options_tweet` and structured `options_context` (contracts/side/score) for options-focused filtering and UI routing.
- Options tweet delivery now supports backend feed filtering (`options_only=true`) on both `/api/posts` and `/api/stream` for route-level isolation.
- NFT migration slice: CoinGecko trending NFTs endpoint (`/api/nfts/trending`) now available.
- Stock migration slice: market session endpoint (`/api/stocks/market-hours`) now available with pre-market/after-hours state mapping for major exchanges.
- Stock market-hours service hardening: short-lived cache plus stale-cache fallback now keeps the endpoint available during transient Yahoo rate limits (`429`).
- Events migration slice: Investing economic calendar endpoint (`/api/events/economic`) now available for high-impact US and Euro-zone events.
- Service-backed endpoints for Fear & Greed, treemap, StockTwits, SPY heatmap, trending crypto, and WallStreetBets Reddit hot posts.
- Reddit WallStreetBets ingestion uses asyncpraw-first (legacy-style credentials) with HTTP JSON fallback when credentials are missing.
- StockTwits service fallback for anti-bot blocks: curl-first fetch strategy with short-lived per-keyword cache fallback to avoid transient 503s (curl is executed via thread-backed sync subprocess for Windows/uvicorn compatibility).
- Portfolio backend for IBKR-style stock tracking: positions CRUD endpoints and live summary valuation/PnL using Yahoo quotes.
- Deployment scaffolding for self-hosting: backend Docker image, frontend Nginx reverse proxy for `/api/*` + `/api/stream`, Docker Compose stack for Raspberry Pi, and Terraform-managed Cloudflare tunnel + DNS.

## Frontend: Implemented

- Live tweet timeline using initial REST load + SSE updates.
- Timeline pagination: initial REST load now requests 200 tweets, with manual load-older pagination wired via `before_id`.
- Quote tweet markdown rendering with quote embed styling.
- Repost handling: retweeted posts now render with original author identity (name/avatar) and explicit reposter attribution line.
- Quote tweet header now mirrors native X styling by showing quoted author identity (instead of a generic label) and quoted timestamp when available.
- Quote tweet header now includes the quoted user's avatar next to their name when image metadata is available.
- Quote embeds now consume backend `quoted_tweet` metadata/media directly (author, handle, timestamp, image), with markdown heuristics only as fallback.
- Subscriber-only posts now render a native-style icon in tweet headers (including reposted originals and quoted tweet headers when marked exclusive).
- Quote image handling inside embed (with main image placement before quote embed).
- Tweet body rendering now preserves original line breaks and intentional blank lines.
- Tweet images now open in an in-page lightbox preview (no full-page navigation away from timeline).
- Tweet timestamps are shown in the viewer's local timezone (UTC source timestamps normalized server-side with offset).
- Financial asset blocks in tweet cards are intentionally compact and now show ticker, full name, type, price, and daily % change.
- Price links to source financial website when available.
- Sidebar filters: all, crypto, stock, non-financial.
- Ticker filtering via:
  - clicking ticker inside financial asset widget,
  - manual typed input in sidebar ticker filter.
- Route-level segmentation pages implemented:
  - `/` home overview,
  - `/crypto` crypto widgets,
  - `/stocks` stock widgets,
  - `/forex` macro/forex widgets,
  - `/nfts` NFT momentum widget,
  - `/portfolio` portfolio management.
- Crypto and stock routes support chart-focused tweet ordering:
  - Latest,
  - Charts first,
  - Charts only.
- Tweet cards display a small "Chart" badge only when backend chart classification marks `has_chart=true`.
- Tweet cards display separate sentiment badges for the main post and quoted post using backend metadata.
- Portfolio route includes add/list/toggle/delete workflows and summary cards (positions, market value, cost basis, unrealized PnL).
- Home route includes a WallStreetBets radar widget with latest Reddit post momentum signals.
- NFTs route includes a CoinGecko-based trending collections widget with floor price and 24h floor change.
- Stocks route now includes a market-hours banner showing major exchange session state (open/pre-market/after-hours/closed).
- Crypto route now includes a Binance movers widget (top gainers/losers).
- Stocks route now includes a Nasdaq trading halts widget.
- Options route now includes a market activity widget for calls, puts, put/call ratio, and most-active contracts.
- Options route timeline now filters to tweets classified as options-intent (`is_options_tweet=true`) instead of generic stock-linked tweets.
- Options route now consumes options-only REST/SSE feeds so only options-classified tweets are fetched and rendered there.
- Forex route now includes an economic events widget backed by Investing high-impact calendar data.
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
- Debug admin panel: `/api/debug/tweet` -> `DebugAdminPanel` (`/admin`).
- Portfolio panel: `/api/portfolio/positions` + `/api/portfolio/summary` -> `PortfolioPanel` (`/portfolio`).
- WallStreetBets panel: `/api/reddit/wsb` -> `RedditWsbWidget` (`/`).
- NFTs panel: `/api/nfts/trending` -> `NftTrendingWidget` (`/nfts`).
- Stock market-hours banner: `/api/stocks/market-hours` -> `StockMarketHoursBanner` (`/stocks`).
- Economic events panel: `/api/events/economic` -> `EconomicEventsWidget` (`/forex`).

## Backend APIs Not Yet Connected in Main UI

- No known unconnected backend API endpoints from the current `app/api/main.py` surface.

## Suggested Next Connections

- Continue legacy feature migration from `fintwit-bot` domains not yet ported (forex, options volume/SPACs/short-interest slices, NFTs).
