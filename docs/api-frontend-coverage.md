# API and Frontend Coverage Matrix

Last updated: 2026-04-06

## Authentication

- All endpoints under `/api/*` use the same API key dependency.
- If `API_KEY` is configured in backend env, clients must send `X-API-Key`.

## Endpoint Matrix

| Endpoint | Method | Data Source | Returns | Frontend Status |
| --- | --- | --- | --- | --- |
| `/api/posts` | GET | SQLite via `TweetRepo.latest` | Latest tweets including `assets`, engagement, media, symbols, and sentiment metadata for both main and quoted text (`sentiment_*`, `quoted_sentiment_*`) | Connected via `useTweets` |
| `/api/stream` | GET (SSE) | In-memory broadcaster from stream worker | Real-time tweet/new engagement updates (including main + quoted sentiment metadata on new tweets) | Connected via `useTweets` |
| `/api/fear-greed` | GET | `alternative.me/fng` | `{ value, change, status }` | Connected via `FearGreedWidget` |
| `/api/treemap` | GET | `coin360.com/site-api/coins` | Coin360 top-100 treemap payload | Connected via `TreemapWidget` |
| `/api/trending-crypto` | GET | `coinmarketcap.com/data-api/v3/topsearch/rank` | List of trending coins with price/change/volume/website | Connected via `TrendingCryptoWidget` |
| `/api/stocktwits` | GET | `api.stocktwits.com/api/2/charts/{keyword}` (curl-first, then httpx; short-lived cache fallback on transient failures) | Formatted StockTwits rank list (`symbol`, `name`, `price`, `val`); returns `[]` during transient upstream unavailability | Connected via `StocktwitsWidget` |
| `/api/spy-heatmap` | GET | `phx.unusualwhales.com/api/etf/SPY/heatmap` | SPY heatmap JSON by date range | Connected via `SpyHeatmapWidget` |
| `/api/reddit/wsb` | GET | `asyncpraw` (credentials via env) with fallback to `reddit.com/r/{subreddit}/hot.json` via `httpx` | Recent non-stickied Reddit hot posts with title/body/media normalization | Connected via `RedditWsbWidget` |
| `/api/portfolio/positions` | GET | SQLite via `PortfolioRepo.list_positions` | Portfolio positions list | Connected via `usePortfolio` / `PortfolioPanel` |
| `/api/portfolio/positions` | POST | SQLite via `PortfolioRepo.create_position` | Created portfolio position | Connected via `usePortfolio` / `PortfolioPanel` |
| `/api/portfolio/positions/{position_id}` | PATCH | SQLite via `PortfolioRepo.update_position` | Updated portfolio position (active flag and editable fields) | Connected via `usePortfolio` / `PortfolioPanel` |
| `/api/portfolio/positions/{position_id}` | DELETE | SQLite via `PortfolioRepo.delete_position` | `{ ok: true }` on delete | Connected via `usePortfolio` / `PortfolioPanel` |
| `/api/portfolio/summary` | GET | SQLite positions + Yahoo Finance (`get_stock_info`) | Live valuation totals and per-position unrealized PnL | Connected via `usePortfolio` / `PortfolioPanel` |
| `/api/debug/tweet` | POST | Internal debug helper + enrichment | Injected tweet payload persisted + broadcast | Connected via `DebugAdminPanel` (`/admin`) |

## Enrichment Data Flow (Indirect APIs)

These services are not exposed as standalone endpoints, but are used in asset enrichment for tweets:

- Yahoo Finance (`query1.finance.yahoo.com`) for equities:
  - returns `price`, `change_percent`, `volume`, `website`.
- CoinGecko (`api.coingecko.com`) for crypto:
  - returns `price`, `change_percent`, `volume`, `website`.
- FinTwitBERT sentiment (`StephanAkkerman/FinTwitBERT-sentiment`) for tweet text:
  - returns separate main-post and quoted-post sentiment fields (`sentiment_*`, `quoted_sentiment_*`).
  - historical tweets can be backfilled via `python -m app.runtime.backfill_sentiment`.

The enriched values are attached under `tweet.assets[*].financials` and consumed in `TweetCard`.

## Frontend Contract Notes

- Route-level sections are path-based and mounted in `App.tsx`:
  - `/` home overview,
  - `/crypto` crypto-focused widgets,
  - `/stocks` stock-focused widgets,
  - `/portfolio` portfolio management.

- Primary contracts live in `frontend/src/types.ts` (tweets, market widgets, and portfolio types).
- Timeline and filters rely on:
  - `tickers`, `hashtags`, and symbol extraction from text,
  - `assets[].symbol` and `assets[].kind` for category and ticker filters,
  - `assets[].financials.website` for price links,
  - `sentiment_*` for main-post sentiment rendering,
  - `quoted_sentiment_*` for quote-post sentiment rendering.
