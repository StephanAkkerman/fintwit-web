# Phase 2 follow-up — Track record / move-since-mention (📊)

Status: **deferred / not built**
Parent feature: per-tweet ticker mention-frequency indicators (the "Mentions" strip),
shipped 2026-06-12 — see `app/services/mention_aggregator.get_mention_frequency`,
`POST /api/overview/mention-frequency`, `frontend/src/hooks/useMentionFrequency.ts`,
and `frontend/src/components/MentionsStrip.tsx`.

## Goal

Add a 📊 indicator that answers *"how have this author's past calls on this ticker
actually performed?"* — e.g. tooltip *"first flagged $95, now $120 (+26%)"*, or an
average move since their mentions over the window. This reframes the strip from
"how much / how convinced" to "how well," which is the highest-value question for
evaluating a trader.

## Why it was deferred

It depends entirely on `assets[*].financials.price` being reliably present on
**historical** tweets — the same field `get_mention_heat`'s `price_direction`
already leans on. Asset/price enrichment was added partway through the project, so
older tweets may have null prices. If coverage is sparse, the indicator degrades to
"N/A" and is not worth surfacing.

## First step (gate) — verify historical price coverage

Before building anything, measure how often `assets[*].financials.price` is populated
across the tweet history, bucketed by age. Rough check:

```sql
SELECT
  CAST((julianday('now') - julianday(t.created_at)) / 7 AS INT) AS weeks_ago,
  COUNT(*) AS ticker_rows,
  SUM(CASE WHEN json_extract(ae.value, '$.financials.price') IS NOT NULL
           THEN 1 ELSE 0 END) AS with_price
FROM tweets t, json_each(t.tickers) j
LEFT JOIN json_each(t.assets) ae
       ON json_extract(ae.value, '$.symbol') = j.value
WHERE t.tickers IS NOT NULL AND t.tickers != '[]'
GROUP BY weeks_ago
ORDER BY weeks_ago;
```

Decision rule: if price coverage holds up across the 30d window (say ≥60% of
ticker-rows have a price), proceed. Otherwise, either (a) skip 📊, or (b) first run a
historical price backfill (analogous to `app/runtime/backfill_sentiment.py`) keyed on
ticker + tweet date, then re-measure.

## Sketch (only if the gate passes)

- Extend `get_mention_frequency`'s per-scope aggregate with the author's
  earliest-in-window mention price and a current price (reuse the
  `price_recent` / `price_at_start` CTE pattern from `get_mention_heat`).
- Add `move_since_first_pct` (and optionally `avg_move_pct`) to `TickerScopeStat`.
- In `MentionsStrip`, append 📊 with a tooltip; keep it a *modifier* on already-notable
  rows (do not let it create rows on its own in v2 either).
