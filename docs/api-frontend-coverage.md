# API and Frontend Coverage Matrix

Last updated: 2026-04-04

## Authentication

- All endpoints under `/api/*` use the same API key dependency.
- If `API_KEY` is configured in backend env, clients must send `X-API-Key`.

## Endpoint Matrix

| Endpoint | Method | Data Source | Returns | Frontend Status |
| --- | --- | --- | --- | --- |
| `/api/posts` | GET | SQLite via `TweetRepo.latest` | Latest tweets including `assets`, engagement, media, symbols | Connected via `useTweets` |
| `/api/stream` | GET (SSE) | In-memory broadcaster from stream worker | Real-time tweet/new engagement updates | Connected via `useTweets` |
| `/api/fear-greed` | GET | `alternative.me/fng` | `{ value, change, status }` | Connected via `FearGreedWidget` |
| `/api/treemap` | GET | `coin360.com/site-api/coins` | Coin360 top-100 treemap payload | Connected via `TreemapWidget` |
| `/api/trending-crypto` | GET | `coinmarketcap.com/data-api/v3/topsearch/rank` | List of trending coins with price/change/volume/website | Connected via `TrendingCryptoWidget` |
| `/api/stocktwits` | GET | `api.stocktwits.com/api/2/charts/{keyword}` (curl-first, then httpx; short-lived cache fallback on transient failures) | Formatted StockTwits rank list (`symbol`, `name`, `price`, `val`); returns `[]` during transient upstream unavailability | Connected via `StocktwitsWidget` |
| `/api/spy-heatmap` | GET | `phx.unusualwhales.com/api/etf/SPY/heatmap` | SPY heatmap JSON by date range | Connected via `SpyHeatmapWidget` |
| `/api/debug/tweet` | POST | Internal debug helper + enrichment | Injected tweet payload persisted + broadcast | Connected via `DebugAdminPanel` (`/admin`) |

## Enrichment Data Flow (Indirect APIs)

These services are not exposed as standalone endpoints, but are used in asset enrichment for tweets:

- Yahoo Finance (`query1.finance.yahoo.com`) for equities:
  - returns `price`, `change_percent`, `volume`, `website`.
- CoinGecko (`api.coingecko.com`) for crypto:
  - returns `price`, `change_percent`, `volume`, `website`.

The enriched values are attached under `tweet.assets[*].financials` and consumed in `TweetCard`.

## Frontend Contract Notes

- Route-level sections are path-based and mounted in `App.tsx`:
  - `/` home overview,
  - `/crypto` crypto-focused widgets,
  - `/stocks` stock-focused widgets.

- Primary tweet contract lives in `frontend/src/types.ts` (`Tweet`, `Asset`, `AssetFinancials`).
- Timeline and filters rely on:
  - `tickers`, `hashtags`, and symbol extraction from text,
  - `assets[].symbol` and `assets[].kind` for category and ticker filters,
  - `assets[].financials.website` for price links.
