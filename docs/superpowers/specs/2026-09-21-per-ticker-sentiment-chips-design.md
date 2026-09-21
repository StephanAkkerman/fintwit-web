# Per-ticker sentiment chips — design

**Date:** 2026-09-21
**Status:** Approved

## Goal

Surface the per-ticker sentiment split that `app/ml/sentiment.py` already computes
(a tweet that is long one ticker and short another) on the tweet card, instead of
showing only one whole-post bullish/bearish/neutral badge that averages the two
away.

## Background

The backend already does the hard part. `FinTwitSentiment._classify_sync`
(`app/ml/sentiment.py:265-289`) splits a tweet's own text into segments, scores each,
and attributes segments to tickers via `attribute_segments`. It stores the result as:

- `sentiment_label` / `sentiment_emoji` / `sentiment_score` — the post's overall
  verdict (mean of all segments), unchanged from before this feature.
- `ticker_sentiment: Record<string, number>` — **sparse**: only holds an entry for a
  ticker whose mean segment score differs from the overall score. A ticker not in
  this map reads the same as the post overall.

This map only ever reflects the author's own text — `classify_parts`
(`app/ml/sentiment.py:291-318`) never attributes segments from a quoted tweet, since
a quote is someone else's opinion.

`frontend/src/types.ts:168-186` already declares `ticker_sentiment` on `Tweet`, and
`useTweets.ts` passes it through untouched (no transformation layer to change), but
`TweetCard.tsx` never reads it:

- The single footer badge (`TweetCard.tsx:793-806`) renders only
  `t.sentiment_label` / `t.sentiment_emoji`.
- Each asset card (`TweetCard.tsx:651-767`, one per mentioned ticker, with price,
  fundamentals, TA, Signa, StockTwits sentiment) has no sentiment indicator at all.

The gap: a post like "Long $NVDA here, short $INTC into earnings" currently shows
one NEUTRAL badge (the average of a strongly bullish and a strongly bearish
segment) — actively misleading, since neither ticker is neutral.

## Design

### 1. New shared helper: `frontend/src/utils/sentiment.ts`

Pure functions, no React, no network — mirrors the backend's bucketing so both
sides agree on what counts as bullish/bearish/neutral:

```ts
export type SentimentLabel = 'BULLISH' | 'BEARISH' | 'NEUTRAL'

// Mirrors app/ml/sentiment.py SENTIMENT_THRESHOLD (0.1) / label_from_score.
export function labelFromScore(score: number): SentimentLabel {
  if (score > 0.1) return 'BULLISH'
  if (score < -0.1) return 'BEARISH'
  return 'NEUTRAL'
}

// Mirrors app/ml/sentiment.py LABEL_TO_EMOJI.
export function emojiForLabel(label: SentimentLabel): string {
  return { BULLISH: '🐂', BEARISH: '🐻', NEUTRAL: '🦆' }[label]
}

// The pill classes currently inlined 2x in TweetCard.tsx (main + quoted badge);
// a 3rd inline copy would be needed for the per-ticker chip, so extract instead.
export function sentimentBadgeClass(label: SentimentLabel): string {
  return {
    BULLISH: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
    BEARISH: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300',
    NEUTRAL: 'bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200',
  }[label]
}

// Sparse-override contract: a ticker not in ticker_sentiment reads as the
// post's own overall score.
export function effectiveTickerScore(
  overallScore: number | null | undefined,
  tickerSentiment: Record<string, number> | null | undefined,
  symbol: string
): number {
  return tickerSentiment?.[symbol.toUpperCase()] ?? overallScore ?? 0
}
```

No backend or DB change. `ticker_sentiment` keeps its current raw
`{ticker: signedScore}` shape; bucketing into a label/emoji happens only at render
time, exactly as `sentiment_score` is already bucketed into `sentiment_label` today
(just done in Python instead of duplicated in two places).

### 2. `TweetCard.tsx` changes

- `hasSplit` is **not** `Object.keys(t.ticker_sentiment ?? {}).length > 0`. Presence
  in `ticker_sentiment` only means a ticker's mean *score* differs from the overall
  score (`app/ml/sentiment.py`'s `mean != round(overall, 4)` check) — it says nothing
  about whether the two *labels* differ, and two different scores routinely bucket to
  the same label through `labelFromScore`'s ±0.1 threshold (e.g. overall `0.455`
  BULLISH, ticker `0.91` also BULLISH). So `hasSplit` must independently recompute
  `labelFromScore` for the overall score and for each ticker's score and compare
  those labels:
  ```ts
  const overallLabel = labelFromScore(t.sentiment_score ?? 0)
  const diverging = Object.entries(t.ticker_sentiment ?? {}).filter(
    ([, score]) => labelFromScore(score) !== overallLabel
  )
  const hasSplit = diverging.length > 0
  ```
  computed once per tweet alongside the existing `sentimentLabel`/`sentimentEmoji`
  derivations (`TweetCard.tsx:389-392`).
- Replace the three inline `sentimentClass`/`quotedSentimentClass` ternaries
  (`TweetCard.tsx:408-419`) with calls to `sentimentBadgeClass`.
- **Per-ticker chip** — in the `assets.map(...)` block (`TweetCard.tsx:651-767`),
  next to the existing `$NVDA` ticker button/label (`TweetCard.tsx:690-704`), render
  a chip when `hasSplit` is true, for **every** mapped asset (not just the ones the
  backend flagged as divergent — a ticker with no override still gets a chip using
  the post's overall score, so all mentioned tickers are visually comparable
  side by side):
  ```tsx
  {hasSplit && (
    <span
      aria-label={`Sentiment for $${asset.symbol.toUpperCase()}: ${label}`}
      title={`Confidence: ${(Math.abs(score) * 100).toFixed(1)}%`}
      className="text-sm"
    >
      {emojiForLabel(label)}
    </span>
  )}
  ```
  where `score = effectiveTickerScore(t.sentiment_score, t.ticker_sentiment, asset.symbol)`
  and `label = labelFromScore(score)`.
- **Footer badge** (`TweetCard.tsx:793-806`) — when `hasSplit` is true, render a
  compact "Mixed" chip instead of the averaged label/emoji:
  ```tsx
  {hasSplit ? (
    <span
      aria-label="Tweet sentiment: mixed by ticker"
      title={diverging
        .map(([sym, sc]) => `${sym}: ${displayLabel(labelFromScore(sc))}`)
        .join(' · ')}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${sentimentBadgeClass(null)}`}
    >
      <span>🔀</span>
      <span>MIXED</span>
    </span>
  ) : (
    (sentimentLabel || sentimentEmoji) && ( /* unchanged existing badge */ )
  )}
  ```
  The tooltip lists only the tickers in `diverging` — i.e. the ones whose
  `labelFromScore` actually disagrees with the overall label, which is why the post
  reads as mixed. This is **not** the same set as "keys present in `ticker_sentiment`":
  that map is sparse by score, not by label, so it can (and in practice does) contain
  tickers whose score differs from the overall score but whose label does not. Those
  tickers are not divergent, are not counted toward `hasSplit`, and are not listed in
  the tooltip — the frontend must filter by label before treating anything as
  "mixed," never trust key-presence alone.
- The quoted-tweet badge (`quotedSentimentLabel`/`quotedSentimentEmoji`) is
  untouched — splitting only ever applies to the author's own text.
- Non-split tweets (`hasSplit === false`, the common case): zero rendered
  difference from today — same single footer badge, no chips on asset cards.
- A ticker key present in `ticker_sentiment` with no matching asset card
  (enrichment failed to build a priced card for it) is not given an orphan chip
  anywhere; it still appears in the footer "Mixed" tooltip.

### 3. Out of scope

- `AssetBadge.tsx` — takes only `{ asset: Asset }` with no tweet context, so it has
  no tweet text to attribute a per-ticker score to. Per-ticker sentiment is
  inherently a property of *this tweet's* text about a ticker, not of the ticker
  itself, so it cannot render here regardless of `Asset`'s shape.
- Any backend change. `ticker_sentiment` already has everything needed.
- Quoted-tweet per-ticker splitting (the model deliberately never attributes quoted
  text to tickers).

## Testing

- `frontend/src/utils/sentiment.test.ts` (new): boundary tests at exactly `0.1` /
  `-0.1` / `0`, emoji and badge-class mapping for all three labels, and
  `effectiveTickerScore` for the override-present / override-absent / no-tickers-
  at-all cases.
- `TweetCard.test.tsx`: extend with two fixtures —
  - a split tweet (`ticker_sentiment: { INTC: -0.85 }`, `sentiment_score: 0.6` on a
    tweet mentioning both NVDA and INTC) — assert NVDA's chip shows the overall
    (bullish) reading, INTC's chip shows its own (bearish) override, and the footer
    shows "MIXED" with the INTC-only tooltip.
  - a non-split tweet — assert output is byte-for-byte unchanged from the current
    single-badge footer (no chips rendered).
- `scripts/screenshot_ui.py`: give one sample tweet in the `loaded` fixture a
  `ticker_sentiment` split so `make screenshot` visually captures the chips and the
  "Mixed" footer badge without needing a new scenario.

## Docs

Per `AGENTS.md` §"Documentation Is Required" (frontend feature wiring changes):

- `docs/api-frontend-coverage.md` — move `ticker_sentiment` from "API field
  documented but not consumed by the frontend" to "consumed by `TweetCard` (per-
  ticker sentiment chips)".
- `docs/frontend-integration-map.md` — note the new chip + "Mixed" footer behavior
  on the tweet card.
- `docs/migration-status.md` — no change; no new backend capability or endpoint is
  added, only frontend consumption of an existing field.
