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

## Implemented but Currently Unmounted

- `TreemapWidget` + `useTreemap`
  - Fetches: `/api/treemap`
  - Status: ready, not included in `App.tsx` render tree.

- `TrendingCryptoWidget`
  - Fetches: `/api/trending-crypto`
  - Status: ready, not included in `App.tsx` render tree.

- `MarketOverview` + `useMarketAssets` + `AssetBadge`
  - Fetches: `/api/posts` + `/api/stream` to maintain live top assets list.
  - Status: ready, not included in `App.tsx` render tree.

## Reuse Guidance

- Prefer adding new widgets as isolated components with a dedicated hook per endpoint.
- Keep endpoint contracts mirrored in `frontend/src/types.ts`.
- For any new endpoint connection, add:
  - one component-level test (render/data states),
  - one integration-style test in `App.test.tsx` if mounted in `App`.
