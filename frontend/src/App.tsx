import { useMemo, useState } from 'react'
import FearGreedWidget from './components/FearGreedWidget'
import TweetCard from './components/TweetCard'
import { useTweets } from './hooks/useTweets'
import type { Tweet } from './types'

type FilterKey = 'all' | 'crypto' | 'stock' | 'non-financial'

const FILTERS: Array<{ key: FilterKey; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'crypto', label: 'Crypto' },
  { key: 'stock', label: 'Stock' },
  { key: 'non-financial', label: 'Non-financial' },
]

function isCryptoKind(kind: string | null | undefined): boolean {
  return (kind ?? '').toUpperCase().includes('CRYPTO')
}

function hasTickerLikeText(text: string): boolean {
  return /(^|\s)\$[A-Za-z][A-Za-z0-9]{0,9}\b/.test(text)
}

function extractTickersFromText(text: string): string[] {
  return [...text.matchAll(/(^|\s)\$([A-Za-z][A-Za-z0-9]{0,9})\b/g)].map((m) =>
    m[2].toUpperCase()
  )
}

function matchesTicker(tweet: Tweet, ticker: string): boolean {
  const target = ticker.toUpperCase()
  const fromTickers = (tweet.tickers ?? []).map((t) => t.toUpperCase())
  const fromAssets = (tweet.assets ?? []).map((asset) => asset.symbol.toUpperCase())
  const fromText = extractTickersFromText(tweet.text ?? '')
  return [...fromTickers, ...fromAssets, ...fromText].includes(target)
}

function matchesFilter(tweet: Tweet, filter: FilterKey): boolean {
  if (filter === 'all') return true

  const assets = tweet.assets ?? []
  const hasFinancialSignals =
    assets.length > 0 ||
    (tweet.tickers?.length ?? 0) > 0 ||
    hasTickerLikeText(tweet.text ?? '')
  const hasCrypto = assets.some((asset) => isCryptoKind(asset.kind))
  const hasStock =
    assets.some((asset) => !isCryptoKind(asset.kind)) ||
    (assets.length === 0 && hasFinancialSignals)

  if (filter === 'crypto') return hasCrypto
  if (filter === 'stock') return hasStock
  return !hasFinancialSignals
}

export default function App() {
  const { tweets } = useTweets('') // same-origin API (proxied in dev)
  const [activeFilter, setActiveFilter] = useState<FilterKey>('all')
  const [tickerFilter, setTickerFilter] = useState<string | null>(null)

  const counts = useMemo(
    () => ({
      all: tweets.length,
      crypto: tweets.filter((tweet) => matchesFilter(tweet, 'crypto')).length,
      stock: tweets.filter((tweet) => matchesFilter(tweet, 'stock')).length,
      'non-financial': tweets.filter((tweet) => matchesFilter(tweet, 'non-financial')).length,
    }),
    [tweets]
  )

  const filteredTweets = useMemo(
    () =>
      tweets.filter(
        (tweet) =>
          matchesFilter(tweet, activeFilter) &&
          (!tickerFilter || matchesTicker(tweet, tickerFilter))
      ),
    [tweets, activeFilter, tickerFilter]
  )

  const onTickerSelect = (ticker: string) => {
    setActiveFilter('all')
    setTickerFilter((current) => (current === ticker ? null : ticker))
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black text-zinc-900 dark:text-zinc-100">
      <main className="mx-auto max-w-6xl p-4">
        <div className="grid gap-4 lg:grid-cols-[15rem_minmax(0,1fr)]">
          <aside className="h-fit rounded-2xl border border-zinc-200 bg-white/80 p-3 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/70 lg:sticky lg:top-4">
            <h2 className="px-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">Filters</h2>
            <div className="mt-2 flex flex-col gap-1">
              {FILTERS.map((filter) => {
                const active = filter.key === activeFilter
                return (
                  <button
                    key={filter.key}
                    type="button"
                    onClick={() => setActiveFilter(filter.key)}
                    className={`flex items-center justify-between rounded-xl px-3 py-2 text-sm transition-colors ${
                      active
                        ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                        : 'hover:bg-zinc-100 dark:hover:bg-zinc-800'
                    }`}
                  >
                    <span>{filter.label}</span>
                    <span className={`rounded-full px-2 py-0.5 text-xs ${active ? 'bg-white/20 dark:bg-black/10' : 'bg-zinc-200 dark:bg-zinc-700'}`}>
                      {counts[filter.key]}
                    </span>
                  </button>
                )
              })}
            </div>

            <div className="mt-4 border-t border-zinc-200 pt-3 dark:border-zinc-800">
              <h3 className="px-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                Ticker
              </h3>
              {tickerFilter ? (
                <div className="mt-2 flex items-center gap-2 px-2">
                  <span className="rounded-full bg-zinc-900 px-2 py-1 text-xs font-semibold text-white dark:bg-zinc-100 dark:text-zinc-900">
                    ${tickerFilter}
                  </span>
                  <button
                    type="button"
                    onClick={() => setTickerFilter(null)}
                    className="text-xs text-zinc-500 hover:underline"
                  >
                    Clear
                  </button>
                </div>
              ) : (
                <p className="mt-2 px-2 text-xs text-zinc-500">Click a ticker in a tweet to filter.</p>
              )}
            </div>
          </aside>

          <section className="space-y-3 min-w-0">
            <header className="sticky top-0 z-10 bg-inherit/60 backdrop-blur p-2 -mx-2">
              <h1 className="text-2xl font-bold">X Stream</h1>
              <p className="text-sm text-zinc-500">Live tweets · SSE · Vite</p>
            </header>
            <FearGreedWidget />
            {filteredTweets.map((t) => (
              <TweetCard key={t.id} t={t} onTickerSelect={onTickerSelect} />
            ))}
            {filteredTweets.length === 0 && (
              <div className="rounded-2xl border border-dashed border-zinc-300 bg-white/70 p-5 text-sm text-zinc-500 dark:border-zinc-700 dark:bg-zinc-900/60 dark:text-zinc-400">
                No tweets in this filter yet.
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  )
}