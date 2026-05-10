# Timeframe-Anchored Price Direction Design

**Date:** 2026-05-10  
**Scope:** `app/services/mention_aggregator.py` — `get_mention_heat` only  
**Status:** Approved

## Problem

`price_direction` in `MentionHeatCell` is currently computed as `AVG(financials.change_percent)` across all tweets for a ticker within the selected window. This averages the *intraday change at the time each tweet was posted*, which does not reflect how much the price actually moved over the selected window period.

## Goal

`price_direction` should represent the actual percentage return over the selected window:

```
price_direction = (price_now − price_then) / price_then × 100
```

Where:
- `price_now` = `financials.price` from the most recent tweet mentioning that ticker that has a non-null price
- `price_then` = `financials.price` from the tweet whose `created_at` is closest in time to `now − window_hours`
- This applies uniformly to all three windows: 24h, 48h, 168h

## Implementation

### File changed

`app/services/mention_aggregator.py` — `get_mention_heat` function only.

### SQL structure

Replace the existing flat query with a 3-CTE query:

```sql
WITH
price_recent AS (
    -- Most recent tweet with a non-null financials.price per ticker
    SELECT j.value AS ticker,
           json_extract(ae.value, '$.financials.price') AS price,
           ROW_NUMBER() OVER (
               PARTITION BY j.value
               ORDER BY t.created_at DESC
           ) AS rn
    FROM tweets t, json_each(t.tickers) j
    LEFT JOIN json_each(t.assets) ae
           ON json_extract(ae.value, '$.symbol') = j.value
    WHERE json_extract(ae.value, '$.financials.price') IS NOT NULL
      AND t.tickers IS NOT NULL AND t.tickers != '[]'
),
price_at_start AS (
    -- Tweet whose created_at is closest to (now - window_hours) per ticker
    SELECT j.value AS ticker,
           json_extract(ae.value, '$.financials.price') AS price,
           ROW_NUMBER() OVER (
               PARTITION BY j.value
               ORDER BY ABS(julianday(t.created_at) - julianday(:cutoff))
           ) AS rn
    FROM tweets t, json_each(t.tickers) j
    LEFT JOIN json_each(t.assets) ae
           ON json_extract(ae.value, '$.symbol') = j.value
    WHERE json_extract(ae.value, '$.financials.price') IS NOT NULL
      AND t.tickers IS NOT NULL AND t.tickers != '[]'
),
mentions AS (
    -- Existing aggregation: count mentions, avg sentiment, max kind
    SELECT j.value AS ticker,
           CAST(COUNT(*) AS INTEGER) AS mentions,
           AVG(t.sentiment_score) AS avg_sentiment_24h,
           MAX(json_extract(ae.value, '$.kind')) AS asset_kind
    FROM tweets t, json_each(t.tickers) j
    LEFT JOIN json_each(t.assets) ae
           ON json_extract(ae.value, '$.symbol') = j.value
    WHERE t.created_at >= :cutoff
      AND t.tickers IS NOT NULL AND t.tickers != '[]'
    GROUP BY j.value
    HAVING 1=1
    {kind_clause}
)
SELECT
    m.ticker,
    m.mentions,
    m.avg_sentiment_24h,
    m.asset_kind,
    CASE
        WHEN pr.price IS NOT NULL
         AND ps.price IS NOT NULL
         AND ps.price != 0
        THEN (pr.price - ps.price) / ps.price * 100.0
        ELSE NULL
    END AS price_direction
FROM mentions m
LEFT JOIN (SELECT ticker, price FROM price_recent  WHERE rn = 1) pr ON pr.ticker = m.ticker
LEFT JOIN (SELECT ticker, price FROM price_at_start WHERE rn = 1) ps ON ps.ticker = m.ticker
ORDER BY m.mentions DESC
LIMIT :limit
```

### Parameters

| Parameter | Value |
|-----------|-------|
| `:cutoff` | `now − window_hours` (same as existing) |
| `:limit`  | unchanged (50) |

### Edge cases

| Scenario | Result |
|----------|--------|
| Ticker has no `financials.price` in any tweet | `price_direction = NULL` |
| Only one tweet matches (price_now == price_then) | `price_direction = 0.0` |
| `price_then = 0` | `price_direction = NULL` (division guard) |
| Sparse data: closest tweet is not near the cutoff | Returns best available — no null penalty |

## No-change zones

- No schema changes
- No frontend changes (`price_direction: number | null` already correct in `types.ts`)
- No API endpoint changes
- `get_sentiment_shift`, `get_volume_baseline`, `get_hidden_gems` — untouched
