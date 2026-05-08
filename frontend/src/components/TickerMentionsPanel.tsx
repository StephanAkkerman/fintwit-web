import { useMemo } from 'react'
import type { Tweet } from '../types'
import { hasChartSignal } from '../utils/tweetSignals'

type TickerMentionsPanelProps = {
  tweets: Tweet[]
  scopeLabel: string
  route: 'home' | 'crypto' | 'stocks' | 'forex' | 'portfolio' | 'options' | 'admin'
  selectedUser?: string | null
  onTickerSelect?: (ticker: string) => void
}

type MentionAggregate = {
  symbol: string
  mentions: number
  bullish: number
  bearish: number
  neutral: number
  chartMentions: number
  engagementTotal: number
  authors: Set<string>
}

type MentionRow = {
  symbol: string
  mentions: number
  share: number
  authorCount: number
  chartMentions: number
  sentimentSkew: number
  avgEngagement: number
}

type MentionInsights = {
  rows: MentionRow[]
  analyzedTweets: number
  tweetsWithMentions: number
  uniqueTickers: number
  totalMentions: number
  chartSignalTweets: number
  topAuthor: string | null
  topChartTicker: string | null
  topEngagementTicker: string | null
}

const tickerRegex = /(^|\s)\$([A-Za-z][A-Za-z0-9]{0,9})\b/g
const validTickerRegex = /^[A-Z][A-Z0-9]{0,9}$/

function normalizeAuthor(tweet: Tweet): string | null {
  const raw = (tweet.user_screen_name ?? tweet.user_name ?? '').trim().replace(/^@+/, '')
  if (!raw) return null
  return raw.toLowerCase()
}

function normalizeSentiment(label: string | null | undefined): 'BULLISH' | 'BEARISH' | 'NEUTRAL' {
  const normalized = (label ?? '').toUpperCase()
  if (normalized === 'BULLISH') return 'BULLISH'
  if (normalized === 'BEARISH') return 'BEARISH'
  return 'NEUTRAL'
}

function extractTickersFromText(text: string): string[] {
  return [...text.matchAll(tickerRegex)].map((match) => match[2].toUpperCase())
}

function getAssetKindsForRoute(route: string): Set<string> {
  if (route === 'crypto') return new Set(['CRYPTO', 'crypto'])
  if (route === 'stocks') return new Set(['EQUITY', 'equity'])
  return new Set() // Empty set means include all
}

function extractTweetTickers(tweet: Tweet, route: string): string[] {
  const symbols = new Set<string>()
  const allowedKinds = getAssetKindsForRoute(route)
  const shouldFilterByKind = allowedKinds.size > 0

  // Extract from assets with kind filtering
  for (const asset of tweet.assets ?? []) {
    const normalized = asset.symbol?.trim().toUpperCase() ?? ''
    if (validTickerRegex.test(normalized)) {
      // If we have kind-based filtering, check the asset kind
      if (shouldFilterByKind && asset.kind) {
        if (allowedKinds.has(asset.kind)) symbols.add(normalized)
      } else if (!shouldFilterByKind) {
        // If no kind-based filtering for this route, include all
        symbols.add(normalized)
      }
    }
  }

  // For tickers array and text-extracted tickers, only include if we're not doing strict kind filtering
  // or if it's a route where we should include all
  if (!shouldFilterByKind) {
    for (const ticker of tweet.tickers ?? []) {
      const normalized = ticker.trim().toUpperCase()
      if (validTickerRegex.test(normalized)) symbols.add(normalized)
    }

    for (const hashtag of tweet.hashtags ?? []) {
      const normalized = hashtag.trim().replace(/^#/, '').toUpperCase()
      if (validTickerRegex.test(normalized)) symbols.add(normalized)
    }

    for (const ticker of extractTickersFromText(tweet.text ?? '')) {
      if (validTickerRegex.test(ticker)) symbols.add(ticker)
    }
  }

  return [...symbols]
}

function buildMentionInsights(tweets: Tweet[], route: string): MentionInsights {
  const mentionMap = new Map<string, MentionAggregate>()
  const authorCounts = new Map<string, number>()

  let tweetsWithMentions = 0
  let chartSignalTweets = 0

  for (const tweet of tweets) {
    const isChartTweet = hasChartSignal(tweet)
    if (isChartTweet) chartSignalTweets += 1

    const symbols = extractTweetTickers(tweet, route)
    if (symbols.length === 0) continue

    tweetsWithMentions += 1

    const author = normalizeAuthor(tweet)
    if (author) {
      authorCounts.set(author, (authorCounts.get(author) ?? 0) + 1)
    }

    const sentiment = normalizeSentiment(tweet.sentiment_label)
    const engagement = (tweet.likes ?? 0) + (tweet.retweets ?? 0) + (tweet.replies ?? 0)

    for (const symbol of symbols) {
      const existing = mentionMap.get(symbol)
      const aggregate: MentionAggregate =
        existing ?? {
          symbol,
          mentions: 0,
          bullish: 0,
          bearish: 0,
          neutral: 0,
          chartMentions: 0,
          engagementTotal: 0,
          authors: new Set<string>(),
        }

      aggregate.mentions += 1
      aggregate.engagementTotal += engagement
      if (isChartTweet) aggregate.chartMentions += 1
      if (sentiment === 'BULLISH') aggregate.bullish += 1
      if (sentiment === 'BEARISH') aggregate.bearish += 1
      if (sentiment === 'NEUTRAL') aggregate.neutral += 1
      if (author) aggregate.authors.add(author)

      mentionMap.set(symbol, aggregate)
    }
  }

  const totalMentions = [...mentionMap.values()].reduce((acc, item) => acc + item.mentions, 0)

  const rows = [...mentionMap.values()]
    .sort((a, b) => {
      if (b.mentions !== a.mentions) return b.mentions - a.mentions
      return a.symbol.localeCompare(b.symbol)
    })
    .map<MentionRow>((item) => ({
      symbol: item.symbol,
      mentions: item.mentions,
      share: totalMentions > 0 ? item.mentions / totalMentions : 0,
      authorCount: item.authors.size,
      chartMentions: item.chartMentions,
      sentimentSkew: item.bullish - item.bearish,
      avgEngagement: item.mentions > 0 ? item.engagementTotal / item.mentions : 0,
    }))

  const topAuthor = [...authorCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null
  const topChartTicker = [...mentionMap.values()].sort((a, b) => b.chartMentions - a.chartMentions)[0]?.symbol ?? null
  const topEngagementTicker = rows
    .slice()
    .sort((a, b) => b.avgEngagement - a.avgEngagement)[0]?.symbol ?? null

  return {
    rows,
    analyzedTweets: tweets.length,
    tweetsWithMentions,
    uniqueTickers: mentionMap.size,
    totalMentions,
    chartSignalTweets,
    topAuthor,
    topChartTicker,
    topEngagementTicker,
  }
}

export default function TickerMentionsPanel({
  tweets,
  scopeLabel,
  route,
  selectedUser,
  onTickerSelect,
}: TickerMentionsPanelProps) {
  const insights = useMemo(() => buildMentionInsights(tweets, route), [tweets, route])
  const topRows = insights.rows.slice(0, 8)
  const maxMentions = topRows[0]?.mentions ?? 1
  const focusLabel = selectedUser ? `@${selectedUser}` : 'all users'

  return (
    <section className="rounded-2xl border border-zinc-200 bg-white/80 p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/70">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-700 dark:text-zinc-200">
            Ticker mention pulse
          </h2>
          <p className="text-xs text-zinc-500">
            From the latest loaded {scopeLabel.toLowerCase()} tweets, focused on {focusLabel}.
          </p>
        </div>
        <div className="rounded-full border border-zinc-200 px-2 py-1 text-[11px] font-semibold text-zinc-600 dark:border-zinc-700 dark:text-zinc-300">
          {topRows.length} / {insights.uniqueTickers} shown
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <div className="rounded-xl bg-zinc-100/80 p-2 dark:bg-zinc-800/70">
          <p className="text-zinc-500">Analyzed tweets</p>
          <p className="mt-0.5 text-sm font-semibold text-zinc-900 dark:text-zinc-100">{insights.analyzedTweets}</p>
        </div>
        <div className="rounded-xl bg-zinc-100/80 p-2 dark:bg-zinc-800/70">
          <p className="text-zinc-500">Tweets with symbols</p>
          <p className="mt-0.5 text-sm font-semibold text-zinc-900 dark:text-zinc-100">{insights.tweetsWithMentions}</p>
        </div>
        <div className="rounded-xl bg-zinc-100/80 p-2 dark:bg-zinc-800/70">
          <p className="text-zinc-500">Total mentions</p>
          <p className="mt-0.5 text-sm font-semibold text-zinc-900 dark:text-zinc-100">{insights.totalMentions}</p>
        </div>
        <div className="rounded-xl bg-zinc-100/80 p-2 dark:bg-zinc-800/70">
          <p className="text-zinc-500">Chart-tagged tweets</p>
          <p className="mt-0.5 text-sm font-semibold text-zinc-900 dark:text-zinc-100">{insights.chartSignalTweets}</p>
        </div>
      </div>

      {topRows.length === 0 ? (
        <div className="mt-3 rounded-xl border border-dashed border-zinc-300 p-3 text-xs text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
          No ticker mentions in the currently loaded tweet set.
        </div>
      ) : (
        <div className="mt-4 space-y-2">
          {topRows.map((row) => {
            const width = Math.max(8, Math.round((row.mentions / maxMentions) * 100))
            const sharePct = Math.round(row.share * 100)
            const skewTone = row.sentimentSkew > 0 ? 'Bullish skew' : row.sentimentSkew < 0 ? 'Bearish skew' : 'Neutral skew'
            return (
              <div key={row.symbol} className="rounded-xl border border-zinc-200 p-2 dark:border-zinc-800">
                <div className="flex items-center justify-between gap-2">
                  <button
                    type="button"
                    onClick={() => onTickerSelect?.(row.symbol)}
                    aria-label={`Filter by analytics ticker $${row.symbol}`}
                    className="rounded-full bg-zinc-900 px-2 py-1 text-xs font-semibold text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
                  >
                    ${row.symbol}
                  </button>
                  <span className="text-xs font-semibold text-zinc-600 dark:text-zinc-300">{row.mentions} mentions</span>
                </div>
                <div className="mt-2 h-2 rounded-full bg-zinc-100 dark:bg-zinc-800">
                  <div
                    className="h-2 rounded-full bg-zinc-600 transition-[width] dark:bg-zinc-300"
                    style={{ width: `${width}%` }}
                  />
                </div>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-zinc-500 dark:text-zinc-400">
                  <span>{sharePct}% share</span>
                  <span>{row.authorCount} voices</span>
                  <span>{row.chartMentions} chart tweets</span>
                  <span>{skewTone}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {topRows.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-zinc-500 dark:text-zinc-400">
          {insights.topAuthor ? (
            <span className="rounded-full border border-zinc-200 px-2 py-1 dark:border-zinc-700">
              Most active author: @{insights.topAuthor}
            </span>
          ) : null}
          {insights.topChartTicker ? (
            <span className="rounded-full border border-zinc-200 px-2 py-1 dark:border-zinc-700">
              Most chart-linked: ${insights.topChartTicker}
            </span>
          ) : null}
          {insights.topEngagementTicker ? (
            <span className="rounded-full border border-zinc-200 px-2 py-1 dark:border-zinc-700">
              Highest avg engagement: ${insights.topEngagementTicker}
            </span>
          ) : null}
        </div>
      )}
    </section>
  )
}
