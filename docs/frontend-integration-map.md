# Frontend Integration Map

Last updated: 2026-04-04

## Mounted in `App.tsx` Today

- `FearGreedWidget`
  - Fetches: `/api/fear-greed`
  - Purpose: sentiment snapshot card.

- Tweet timeline (`useTweets` + `TweetCard`)
  - Fetches: `/api/posts` and `/api/stream` (SSE)
  - Purpose: live timeline with quote embeds, media, financial cards, and engagement updates.

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

- `MarketOverview` + `useMarketAssets` + `AssetBadge`
  - Fetches: `/api/posts` + `/api/stream` (derived live assets)
  - Purpose: top streamed assets with live price/change links.

- `StocktwitsWidget` + `useStocktwits`
  - Fetches: `/api/stocktwits?keyword=...`
  - Purpose: StockTwits ranking view (trending / active / watched).

## Not Yet Mounted

- No known unmounted widgets in `frontend/src/components/` for currently exposed market endpoints.

## Reuse Guidance

- Prefer adding new widgets as isolated components with a dedicated hook per endpoint.
- Keep endpoint contracts mirrored in `frontend/src/types.ts`.
- For any new endpoint connection, add:
  - one component-level test (render/data states),
  - one integration-style test in `App.test.tsx` if mounted in `App`.
