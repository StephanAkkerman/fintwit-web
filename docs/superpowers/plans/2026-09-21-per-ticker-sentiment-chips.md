# Per-Ticker Sentiment Chips Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show each ticker's own sentiment reading on a tweet, instead of one whole-post badge that averages a split thesis (e.g. "long $NVDA, short $INTC") into a misleading NEUTRAL.

**Architecture:** Frontend-only change. The backend already exposes `Tweet.ticker_sentiment: Record<string, number>` (sparse — only present for tickers whose reading differs from the post's overall `sentiment_score`). Add a small pure-function util that mirrors the backend's score→label bucketing, then use it in `TweetCard.tsx` to render an inline emoji chip on every asset card and swap the footer's averaged badge for a "Mixed" indicator whenever a split exists.

**Tech Stack:** React 18 + TypeScript (strict), Vite, Vitest + Testing Library, Tailwind CSS.

## Global Constraints

- No backend, DB, or schema change. `ticker_sentiment` keeps its exact current shape (`Record<string, number> | null`, sparse override semantics) — spec decision, see `docs/superpowers/specs/2026-09-21-per-ticker-sentiment-chips-design.md`.
- TypeScript strict mode (`frontend/tsconfig`) — no `any`; `npx tsc --noEmit` must pass.
- Reuse the exact existing Tailwind pill classes for each sentiment label, unchanged:
  - Bullish: `bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300`
  - Bearish: `bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300`
  - Neutral: `bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200`
- Sentiment threshold mirrors `app/ml/sentiment.py`'s `SENTIMENT_THRESHOLD = 0.1` and `label_from_score`: `score > 0.1` → BULLISH, `score < -0.1` → BEARISH, else NEUTRAL.
- Non-split tweets (the common case, `ticker_sentiment` empty/absent) must render byte-for-byte identically to today — this feature is purely additive for split tweets.
- Per `AGENTS.md` §"Documentation Is Required," any change to frontend feature wiring must update `docs/api-frontend-coverage.md` and `docs/frontend-integration-map.md`.
- Any modified `.py` file must pass `ruff check` and `ruff format --check` (line length 88, rule set `E4,E7,E9,F`).

---

### Task 1: `sentiment.ts` util — score bucketing and shared badge styling

**Files:**
- Create: `frontend/src/utils/sentiment.ts`
- Test: `frontend/src/__tests__/sentiment.test.ts`

**Interfaces:**
- Produces (used by Tasks 2–4):
  - `export type SentimentLabel = 'BULLISH' | 'BEARISH' | 'NEUTRAL'`
  - `export function labelFromScore(score: number): SentimentLabel`
  - `export function emojiForLabel(label: SentimentLabel): string`
  - `export function sentimentBadgeClass(label: string | null | undefined): string`
  - `export function effectiveTickerScore(overallScore: number | null | undefined, tickerSentiment: Record<string, number> | null | undefined, symbol: string): number`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/sentiment.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import {
  effectiveTickerScore,
  emojiForLabel,
  labelFromScore,
  sentimentBadgeClass,
} from '../utils/sentiment'

describe('labelFromScore', () => {
  it('labels scores above the threshold as bullish', () => {
    expect(labelFromScore(0.11)).toBe('BULLISH')
    expect(labelFromScore(0.97)).toBe('BULLISH')
  })

  it('labels scores below the negative threshold as bearish', () => {
    expect(labelFromScore(-0.11)).toBe('BEARISH')
    expect(labelFromScore(-0.97)).toBe('BEARISH')
  })

  it('labels scores at or inside the threshold as neutral', () => {
    expect(labelFromScore(0.1)).toBe('NEUTRAL')
    expect(labelFromScore(-0.1)).toBe('NEUTRAL')
    expect(labelFromScore(0)).toBe('NEUTRAL')
  })
})

describe('emojiForLabel', () => {
  it('maps each label to its emoji', () => {
    expect(emojiForLabel('BULLISH')).toBe('🐂')
    expect(emojiForLabel('BEARISH')).toBe('🐻')
    expect(emojiForLabel('NEUTRAL')).toBe('🦆')
  })
})

describe('sentimentBadgeClass', () => {
  it('maps each known label to its pill color classes', () => {
    expect(sentimentBadgeClass('BULLISH')).toContain('emerald')
    expect(sentimentBadgeClass('BEARISH')).toContain('rose')
    expect(sentimentBadgeClass('NEUTRAL')).toContain('zinc')
  })

  it('falls back to the neutral classes for unrecognized or missing labels', () => {
    expect(sentimentBadgeClass('weird-value')).toContain('zinc')
    expect(sentimentBadgeClass(null)).toContain('zinc')
    expect(sentimentBadgeClass(undefined)).toContain('zinc')
  })
})

describe('effectiveTickerScore', () => {
  it('uses the ticker override when present', () => {
    expect(effectiveTickerScore(0.6, { INTC: -0.85 }, 'INTC')).toBe(-0.85)
  })

  it('falls back to the overall score when the ticker has no override', () => {
    expect(effectiveTickerScore(0.6, { INTC: -0.85 }, 'NVDA')).toBe(0.6)
  })

  it('falls back to the overall score when ticker_sentiment is absent entirely', () => {
    expect(effectiveTickerScore(0.6, null, 'NVDA')).toBe(0.6)
    expect(effectiveTickerScore(0.6, undefined, 'NVDA')).toBe(0.6)
  })

  it('defaults to 0 when neither an override nor an overall score exists', () => {
    expect(effectiveTickerScore(null, null, 'NVDA')).toBe(0)
    expect(effectiveTickerScore(undefined, undefined, 'NVDA')).toBe(0)
  })

  it('matches the override case-insensitively against the symbol', () => {
    expect(effectiveTickerScore(0.6, { INTC: -0.85 }, 'intc')).toBe(-0.85)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `frontend/`): `npx vitest run src/__tests__/sentiment.test.ts`
Expected: FAIL — `Cannot find module '../utils/sentiment'`

- [ ] **Step 3: Write the implementation**

Create `frontend/src/utils/sentiment.ts`:

```ts
export type SentimentLabel = 'BULLISH' | 'BEARISH' | 'NEUTRAL'

// Mirrors app/ml/sentiment.py SENTIMENT_THRESHOLD.
const SENTIMENT_THRESHOLD = 0.1

const LABEL_TO_EMOJI: Record<SentimentLabel, string> = {
  BULLISH: '🐂',
  BEARISH: '🐻',
  NEUTRAL: '🦆',
}

const LABEL_TO_BADGE_CLASS: Record<SentimentLabel, string> = {
  BULLISH: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  BEARISH: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300',
  NEUTRAL: 'bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200',
}

/** Mirrors app/ml/sentiment.py's label_from_score (threshold = 0.1). */
export function labelFromScore(score: number): SentimentLabel {
  if (score > SENTIMENT_THRESHOLD) return 'BULLISH'
  if (score < -SENTIMENT_THRESHOLD) return 'BEARISH'
  return 'NEUTRAL'
}

/**
 * Mirrors app/ml/sentiment.py's LABEL_TO_EMOJI. Input must already be one of
 * the three labels (e.g. from `labelFromScore`) — it is not a free-form
 * validator.
 */
export function emojiForLabel(label: SentimentLabel): string {
  return LABEL_TO_EMOJI[label]
}

/**
 * Tailwind pill classes shared by the main, quoted, and per-ticker sentiment
 * badges. Accepts arbitrary backend label text — only 'BULLISH'/'BEARISH' are
 * recognized (matching the API contract); anything else, including null and
 * unrecognized strings, renders as neutral.
 */
export function sentimentBadgeClass(label: string | null | undefined): string {
  return LABEL_TO_BADGE_CLASS[label as SentimentLabel] ?? LABEL_TO_BADGE_CLASS.NEUTRAL
}

/**
 * A ticker absent from `tickerSentiment` reads as the post's own overall
 * score — the sparse-override contract documented on `Tweet.ticker_sentiment`.
 */
export function effectiveTickerScore(
  overallScore: number | null | undefined,
  tickerSentiment: Record<string, number> | null | undefined,
  symbol: string
): number {
  const override = tickerSentiment?.[symbol.toUpperCase()]
  return override ?? overallScore ?? 0
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run src/__tests__/sentiment.test.ts`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/sentiment.ts frontend/src/__tests__/sentiment.test.ts
git commit -m "$(cat <<'EOF'
Add sentiment score-to-label bucketing util

Mirrors app/ml/sentiment.py's threshold and emoji/class mapping so the
frontend can bucket ticker_sentiment's raw scores the same way the
backend already buckets sentiment_score.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Refactor `TweetCard.tsx` to use the shared badge-class helper

Pure refactor, no behavior change — de-duplicates the two inline `sentimentClass`/`quotedSentimentClass` ternaries (soon to be three once the per-ticker chip lands in Task 3) onto `sentimentBadgeClass` from Task 1.

**Files:**
- Modify: `frontend/src/components/TweetCard.tsx`

**Interfaces:**
- Consumes: `sentimentBadgeClass` from Task 1 (`frontend/src/utils/sentiment.ts`)
- Produces: same `sentimentClass` / `quotedSentimentClass` local variable names, same values as before, for Task 4 to keep using.

- [ ] **Step 1: Confirm the baseline is green**

Run (from `frontend/`): `npx vitest run src/__tests__/TweetCard.test.tsx`
Expected: PASS (all existing tests, unchanged)

- [ ] **Step 2: Add the import**

In `frontend/src/components/TweetCard.tsx`, find:

```tsx
import { hasChartSignal } from '../utils/tweetSignals'
```

Replace with:

```tsx
import { hasChartSignal } from '../utils/tweetSignals'
import { sentimentBadgeClass } from '../utils/sentiment'
```

- [ ] **Step 3: Replace the inline ternaries**

Find:

```tsx
  const sentimentClass =
    sentimentLabel === 'BULLISH'
      ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
      : sentimentLabel === 'BEARISH'
        ? 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
        : 'bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200'
  const quotedSentimentClass =
    quotedSentimentLabel === 'BULLISH'
      ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
      : quotedSentimentLabel === 'BEARISH'
        ? 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
        : 'bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200'
```

Replace with:

```tsx
  const sentimentClass = sentimentBadgeClass(sentimentLabel)
  const quotedSentimentClass = sentimentBadgeClass(quotedSentimentLabel)
```

- [ ] **Step 4: Run the test to verify it still passes**

Run: `npx vitest run src/__tests__/TweetCard.test.tsx`
Expected: PASS, same test count as Step 1 — no behavior change.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/TweetCard.tsx
git commit -m "$(cat <<'EOF'
Dedupe sentiment badge classes onto shared util

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Per-ticker sentiment chip on each asset card

**Files:**
- Modify: `frontend/src/components/TweetCard.tsx`
- Test: `frontend/src/__tests__/TweetCard.test.tsx`

**Interfaces:**
- Consumes: `labelFromScore`, `emojiForLabel`, `effectiveTickerScore` from Task 1.
- Produces: `hasTickerSentimentSplit` local variable (component-scope boolean), consumed by Task 4.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/__tests__/TweetCard.test.tsx`, add (after the existing `'renders separate quoted sentiment badge in quote header'` test):

```tsx
  it('shows a per-ticker sentiment chip on every asset card when the tweet has a ticker sentiment split', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          text: 'Long $NVDA here, short $INTC into earnings',
          sentiment_score: 0.6,
          ticker_sentiment: { INTC: -0.85 },
          assets: [
            { symbol: 'NVDA', kind: 'EQUITY', financials: { price: 128.4, change_percent: 2.3 } },
            { symbol: 'INTC', kind: 'EQUITY', financials: { price: 22.1, change_percent: -1.1 } },
          ],
        }}
      />
    )

    // NVDA has no override, so it reads the post's overall (bullish) score.
    expect(screen.getByLabelText('Sentiment for $NVDA: Bullish')).toBeInTheDocument()
    // INTC has its own override, and it disagrees with the overall reading.
    expect(screen.getByLabelText('Sentiment for $INTC: Bearish')).toBeInTheDocument()
  })

  it('does not show per-ticker sentiment chips when the tweet has no ticker sentiment split', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          sentiment_score: 0.6,
          assets: [{ symbol: 'NVDA', kind: 'EQUITY', financials: { price: 128.4, change_percent: 2.3 } }],
        }}
      />
    )

    expect(screen.queryByLabelText(/^Sentiment for \$/)).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npx vitest run src/__tests__/TweetCard.test.tsx -t "sentiment chip"`
Expected: FAIL — `Unable to find an element with the label of: Sentiment for $NVDA: Bullish`

- [ ] **Step 3: Add the import**

In `frontend/src/components/TweetCard.tsx`, find (as left by Task 2):

```tsx
import { sentimentBadgeClass } from '../utils/sentiment'
```

Replace with:

```tsx
import {
  effectiveTickerScore,
  emojiForLabel,
  labelFromScore,
  sentimentBadgeClass,
} from '../utils/sentiment'
```

- [ ] **Step 4: Compute `hasTickerSentimentSplit`**

Find:

```tsx
  const quotedSentimentEmoji = t.quoted_sentiment_emoji ?? null
```

Replace with:

```tsx
  const quotedSentimentEmoji = t.quoted_sentiment_emoji ?? null
  const hasTickerSentimentSplit = Object.keys(t.ticker_sentiment ?? {}).length > 0
```

- [ ] **Step 5: Compute the per-ticker score/label inside the asset map**

Find:

```tsx
            const portfolioStatus = portfolioLookup?.(asset.symbol) ?? null

            return (
```

Replace with:

```tsx
            const portfolioStatus = portfolioLookup?.(asset.symbol) ?? null
            const tickerSentimentScore = effectiveTickerScore(
              t.sentiment_score,
              t.ticker_sentiment,
              asset.symbol
            )
            const tickerSentimentLabel = labelFromScore(tickerSentimentScore)
            const tickerSentimentDisplay =
              tickerSentimentLabel.charAt(0) + tickerSentimentLabel.slice(1).toLowerCase()

            return (
```

- [ ] **Step 6: Render the chip next to the ticker symbol**

Find:

```tsx
                <div className="flex items-center justify-between gap-2">
                  {onTickerSelect ? (
                    <button
                      type="button"
                      onClick={() => onTickerSelect(asset.symbol.toUpperCase())}
                      aria-label={`Filter by $${asset.symbol.toUpperCase()}`}
                      className="truncate text-left font-semibold text-zinc-800 underline-offset-2 hover:underline dark:text-zinc-100"
                    >
                      {ticker}
                    </button>
                  ) : (
                    <div className="truncate font-semibold text-zinc-800 dark:text-zinc-100">
                      {ticker}
                    </div>
                  )}
                  <div className="flex shrink-0 items-center gap-1">
```

Replace with:

```tsx
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-1">
                    {onTickerSelect ? (
                      <button
                        type="button"
                        onClick={() => onTickerSelect(asset.symbol.toUpperCase())}
                        aria-label={`Filter by $${asset.symbol.toUpperCase()}`}
                        className="truncate text-left font-semibold text-zinc-800 underline-offset-2 hover:underline dark:text-zinc-100"
                      >
                        {ticker}
                      </button>
                    ) : (
                      <div className="truncate font-semibold text-zinc-800 dark:text-zinc-100">
                        {ticker}
                      </div>
                    )}
                    {hasTickerSentimentSplit && (
                      <span
                        aria-label={`Sentiment for $${asset.symbol.toUpperCase()}: ${tickerSentimentDisplay}`}
                        title={`Confidence: ${(Math.abs(tickerSentimentScore) * 100).toFixed(1)}%`}
                        className="shrink-0 text-sm"
                      >
                        {emojiForLabel(tickerSentimentLabel)}
                      </span>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `npx vitest run src/__tests__/TweetCard.test.tsx`
Expected: PASS, including the two new tests and every pre-existing test (non-split tweets are unaffected since `hasTickerSentimentSplit` is `false` for them).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/TweetCard.tsx frontend/src/__tests__/TweetCard.test.tsx
git commit -m "$(cat <<'EOF'
Show per-ticker sentiment chip on asset cards

Backend already splits sentiment per ticker (ticker_sentiment), but it
was computed and stored without ever reaching the UI. Every asset card
on a split tweet now gets its own emoji chip: the ticker's override
when the backend flagged one, otherwise the post's overall reading.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Replace the footer badge with a "Mixed" indicator on split tweets

**Files:**
- Modify: `frontend/src/components/TweetCard.tsx`
- Test: `frontend/src/__tests__/TweetCard.test.tsx`

**Interfaces:**
- Consumes: `hasTickerSentimentSplit` and `labelFromScore` from Task 3 / Task 1.

- [ ] **Step 1: Write the failing test**

In `frontend/src/__tests__/TweetCard.test.tsx`, add (after the two tests added in Task 3):

```tsx
  it('replaces the footer sentiment badge with a Mixed indicator when tickers diverge', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          sentiment_label: 'BULLISH',
          sentiment_emoji: '🐂',
          sentiment_score: 0.6,
          ticker_sentiment: { INTC: -0.85 },
          assets: [
            { symbol: 'NVDA', kind: 'EQUITY', financials: { price: 128.4, change_percent: 2.3 } },
            { symbol: 'INTC', kind: 'EQUITY', financials: { price: 22.1, change_percent: -1.1 } },
          ],
        }}
      />
    )

    const mixedBadge = screen.getByLabelText('Tweet sentiment: mixed by ticker')
    expect(mixedBadge).toBeInTheDocument()
    expect(mixedBadge).toHaveAttribute('title', 'INTC: Bearish')
    expect(screen.queryByLabelText('Tweet sentiment')).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run src/__tests__/TweetCard.test.tsx -t "Mixed indicator"`
Expected: FAIL — `Unable to find a label with the text of: Tweet sentiment: mixed by ticker`

- [ ] **Step 3: Implement the footer swap**

In `frontend/src/components/TweetCard.tsx`, find:

```tsx
          {(sentimentLabel || sentimentEmoji) && (
            <span
              aria-label="Tweet sentiment"
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${sentimentClass}`}
              title={
                typeof t.sentiment_score === 'number'
                  ? `Sentiment confidence: ${(t.sentiment_score * 100).toFixed(1)}%`
                  : undefined
              }
            >
              <span>{sentimentEmoji ?? '🦆'}</span>
              <span>{sentimentLabel ?? 'SENTIMENT'}</span>
            </span>
          )}
```

Replace with:

```tsx
          {hasTickerSentimentSplit ? (
            <span
              aria-label="Tweet sentiment: mixed by ticker"
              title={Object.entries(t.ticker_sentiment ?? {})
                .map(([sym, score]) => {
                  const label = labelFromScore(score)
                  return `${sym}: ${label.charAt(0)}${label.slice(1).toLowerCase()}`
                })
                .join(' · ')}
              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200"
            >
              <span>🔀</span>
              <span>MIXED</span>
            </span>
          ) : (
            (sentimentLabel || sentimentEmoji) && (
              <span
                aria-label="Tweet sentiment"
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${sentimentClass}`}
                title={
                  typeof t.sentiment_score === 'number'
                    ? `Sentiment confidence: ${(t.sentiment_score * 100).toFixed(1)}%`
                    : undefined
                }
              >
                <span>{sentimentEmoji ?? '🦆'}</span>
                <span>{sentimentLabel ?? 'SENTIMENT'}</span>
              </span>
            )
          )}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run src/__tests__/TweetCard.test.tsx`
Expected: PASS — the new test, plus every earlier test including `'renders sentiment badge when sentiment fields are available'` and `'renders separate quoted sentiment badge in quote header'` (neither sets `ticker_sentiment`, so `hasTickerSentimentSplit` is `false` and the original badge still renders for them).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/TweetCard.tsx frontend/src/__tests__/TweetCard.test.tsx
git commit -m "$(cat <<'EOF'
Replace footer sentiment badge with Mixed indicator on split tweets

The averaged sentiment_score can read NEUTRAL for a post that is
actually strongly bullish on one ticker and strongly bearish on
another. When ticker_sentiment shows a real split, show a compact
Mixed badge (tooltip lists the divergent tickers) instead of the
misleading average, pointing to the per-ticker chips above.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Screenshot fixture + visual verification

**Files:**
- Modify: `scripts/screenshot_ui.py`

**Interfaces:**
- None (fixture data only; no code consumed by other tasks).

- [ ] **Step 1: Give the NVDA sample tweet a ticker sentiment split**

In `scripts/screenshot_ui.py`, find:

```python
        _sample_tweet(
            1,
            "$NVDA breaking out on huge volume, semis leading the tape today.",
            "Chart Trader",
            "chart_trader",
            ["NVDA"],
            [
                {
                    "symbol": "NVDA",
                    "kind": "EQUITY",
                    "sector": "Technology",
                    "industry": "Semiconductors",
                    "financials": {
                        "price": 184.20,
                        "change_percent": 4.06,
                        "session": "pre-market",
                        "extended_price": 186.75,
                        "extended_change_percent": 5.44,
                    },
                }
            ],
        ),
```

Replace with:

```python
        _sample_tweet(
            1,
            "$NVDA breaking out on huge volume, semis leading the tape today. "
            "Trimming $INTC here though, chart's rolling over.",
            "Chart Trader",
            "chart_trader",
            ["NVDA", "INTC"],
            [
                {
                    "symbol": "NVDA",
                    "kind": "EQUITY",
                    "sector": "Technology",
                    "industry": "Semiconductors",
                    "financials": {
                        "price": 184.20,
                        "change_percent": 4.06,
                        "session": "pre-market",
                        "extended_price": 186.75,
                        "extended_change_percent": 5.44,
                    },
                },
                {
                    "symbol": "INTC",
                    "kind": "EQUITY",
                    "sector": "Technology",
                    "industry": "Semiconductors",
                    "financials": {"price": 22.10, "change_percent": -1.14},
                },
            ],
            ticker_sentiment={"INTC": -0.72},
        ),
```

This keeps the base `sentiment_score` (0.62, bullish) from `_sample_tweet`'s defaults as NVDA's overall reading, and overrides INTC to a bearish -0.72 — the same split the design spec uses as its running example.

- [ ] **Step 2: Lint and format the touched Python file**

Run: `ruff check scripts/screenshot_ui.py && ruff format --check scripts/screenshot_ui.py`
Expected: both PASS with no findings. If `ruff format --check` fails, run `ruff format scripts/screenshot_ui.py` and re-check.

- [ ] **Step 3: Capture the screenshot**

Run (repo root):

```bash
pip install -e ".[dev]"
make screenshot ROUTE=/ SCENARIO=loaded THEME=dark
```

If `make` is not available, run the underlying command directly instead:

```bash
python scripts/screenshot_ui.py --route / --scenario loaded --theme dark
```

Expected output: `artifacts/home-loaded-dark.png`

- [ ] **Step 4: Visually confirm the chips render**

Read `artifacts/home-loaded-dark.png` (via the Read tool, which can view images) and confirm:
- The NVDA card shows a 🐂 chip next to `$NVDA`.
- The INTC card shows a 🐻 chip next to `$INTC`.
- That tweet's footer shows a "MIXED" badge, not a single BULLISH/BEARISH/NEUTRAL badge.
- No other sample tweet's footer badge changed (they have no `ticker_sentiment`).

- [ ] **Step 5: Commit**

```bash
git add scripts/screenshot_ui.py
git commit -m "$(cat <<'EOF'
Add a ticker-sentiment split to the screenshot fixtures

Lets make screenshot capture the new per-ticker chips and Mixed
footer badge without needing a dedicated scenario.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Documentation updates + final verification

**Files:**
- Modify: `docs/api-frontend-coverage.md`
- Modify: `docs/frontend-integration-map.md`

**Interfaces:**
- None (docs only).

- [ ] **Step 1: Update `docs/api-frontend-coverage.md`**

Find:

```
  - `sentiment_*` for main-post sentiment rendering,
  - `quoted_sentiment_*` for quote-post sentiment rendering.
```

Replace with:

```
  - `sentiment_*` for main-post sentiment rendering,
  - `quoted_sentiment_*` for quote-post sentiment rendering,
  - `ticker_sentiment` (falling back to `sentiment_score` per ticker) for a per-ticker sentiment chip on each asset card in `TweetCard`, replacing the single footer sentiment badge with a "Mixed" indicator when any ticker's reading diverges from the post's overall score.
```

- [ ] **Step 2: Update `docs/frontend-integration-map.md`**

Find the sentence fragment (inside the long `TweetCard` feature-list bullet):

```
portfolio-status badges (💼 Held / 🕓 Recently Held) on financial cards whose ticker matches a portfolio position, and engagement updates.
```

Replace with:

```
portfolio-status badges (💼 Held / 🕓 Recently Held) on financial cards whose ticker matches a portfolio position, a per-ticker sentiment chip on each financial card (with a "Mixed" footer badge replacing the single post-level sentiment badge when a tweet's sentiment splits across tickers), and engagement updates.
```

- [ ] **Step 3: Full frontend verification**

Run (from `frontend/`):

```bash
npx tsc --noEmit
npm test
npm run build
```

Expected: all three succeed with no errors.

- [ ] **Step 4: Commit**

```bash
git add docs/api-frontend-coverage.md docs/frontend-integration-map.md
git commit -m "$(cat <<'EOF'
Document per-ticker sentiment chip frontend wiring

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
