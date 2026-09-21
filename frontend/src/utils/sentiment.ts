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
