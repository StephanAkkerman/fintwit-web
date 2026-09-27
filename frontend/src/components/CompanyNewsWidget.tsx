import { useEffect, useMemo, useState } from 'react'
import { useCompanyNews } from '../hooks/useCompanyNews'
import type { CompanyNewsArticle } from '../types'
import { displayLabel, emojiForLabel, sentimentBadgeClass, type SentimentLabel } from '../utils/sentiment'
import NewsSentimentOverview, { fmtScore } from './NewsSentimentOverview'

type SentimentFilter = 'ALL' | SentimentLabel
type SortMode = 'newest' | 'strongest'

const FILTERS: SentimentFilter[] = ['ALL', 'BULLISH', 'NEUTRAL', 'BEARISH']

function dateValue(article: CompanyNewsArticle): number {
  const time = new Date(article.date).getTime()
  return Number.isNaN(time) ? 0 : time
}

function fmtDate(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

type CompanyNewsWidgetProps = {
  /** Ticker clicked elsewhere in the app (tweet card, mention heatmap, etc.). */
  selectedTicker?: string | null
}

export default function CompanyNewsWidget({ selectedTicker }: CompanyNewsWidgetProps = {}) {
  const [symbolInput, setSymbolInput] = useState('AAPL')
  const [symbol, setSymbol] = useState('AAPL')
  const { data, loading, error } = useCompanyNews(symbol)
  const [filter, setFilter] = useState<SentimentFilter>('ALL')
  const [sortMode, setSortMode] = useState<SortMode>('newest')
  const hasSentiment = data.sentiment.analyzed > 0

  // A new symbol starts from the full, newest-first list again.
  useEffect(() => {
    setFilter('ALL')
    setSortMode('newest')
  }, [symbol])

  const visibleArticles = useMemo(() => {
    const filtered =
      filter === 'ALL' ? data.articles : data.articles.filter((article) => article.sentiment_label === filter)
    return [...filtered].sort((a, b) =>
      sortMode === 'strongest'
        ? Math.abs(b.sentiment_score ?? 0) - Math.abs(a.sentiment_score ?? 0)
        : dateValue(b) - dateValue(a)
    )
  }, [data.articles, filter, sortMode])

  const countFor = (key: SentimentFilter): number => {
    if (key === 'ALL') return data.articles.length
    if (key === 'BULLISH') return data.sentiment.bullish
    if (key === 'BEARISH') return data.sentiment.bearish
    return data.sentiment.neutral
  }

  // A ticker click elsewhere (tweet card, mention heatmap, ...) takes over the
  // widget; typing a different symbol here still overrides it. Clearing the
  // global filter (click same ticker again) intentionally does not reset us
  // back to AAPL.
  useEffect(() => {
    const next = (selectedTicker ?? '').trim().toUpperCase()
    if (next && next !== symbol) {
      setSymbol(next)
      setSymbolInput(next)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTicker])

  const submitSymbol = () => {
    const next = symbolInput.trim().toUpperCase()
    if (next) setSymbol(next)
  }

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Company News</h2>
        <div className="flex items-center gap-2">
          <input
            value={symbolInput}
            onChange={(e) => setSymbolInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submitSymbol()
            }}
            placeholder="Symbol"
            className="w-24 rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs uppercase text-zinc-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
          />
          <button
            type="button"
            onClick={submitSymbol}
            className="rounded-md bg-zinc-900 px-2.5 py-1 text-xs font-semibold text-white dark:bg-zinc-100 dark:text-zinc-900"
          >
            Load
          </button>
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-12 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load news for {symbol}.</p>
      ) : data.articles.length === 0 ? (
        <p className="text-sm text-zinc-500">No recent news available for {symbol}.</p>
      ) : (
        <>
          <NewsSentimentOverview symbol={symbol} summary={data.sentiment} articles={data.articles} />
          {hasSentiment && (
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap gap-1" role="group" aria-label="Filter by sentiment">
                {FILTERS.map((key) => (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={filter === key}
                    onClick={() => setFilter(key)}
                    className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                      filter === key
                        ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                        : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
                    }`}
                  >
                    {key === 'ALL' ? 'All' : `${emojiForLabel(key)} ${displayLabel(key)}`} ({countFor(key)})
                  </button>
                ))}
              </div>
              <select
                value={sortMode}
                onChange={(e) => setSortMode(e.target.value as SortMode)}
                aria-label="Sort news"
                className="rounded-md border border-zinc-300 bg-white px-2 py-0.5 text-[11px] text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
              >
                <option value="newest">Newest first</option>
                <option value="strongest">Strongest signal first</option>
              </select>
            </div>
          )}
          {visibleArticles.length === 0 ? (
            <p className="text-sm text-zinc-500">No {displayLabel(filter as SentimentLabel).toLowerCase()} headlines.</p>
          ) : (
            <ul className="space-y-3">
              {visibleArticles.map((article) => (
                <li key={article.url} className="border-b border-zinc-100 pb-3 last:border-0 last:pb-0 dark:border-zinc-900/80">
                  <a
                    href={article.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm font-semibold text-zinc-900 hover:underline dark:text-zinc-100"
                  >
                    {article.title}
                  </a>
                  <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-500">
                    {article.sentiment_label && article.sentiment_score != null && (
                      <span
                        className={`rounded-full px-1.5 py-px font-semibold ${sentimentBadgeClass(article.sentiment_label)}`}
                        title={`FinTwitBERT score ${fmtScore(article.sentiment_score)}`}
                      >
                        {emojiForLabel(article.sentiment_label)} {displayLabel(article.sentiment_label)}
                      </span>
                    )}
                    <span>
                      {article.source ?? 'Unknown source'} &middot; {fmtDate(article.date)}
                    </span>
                  </p>
                  {article.excerpt && (
                    <p className="mt-1 line-clamp-2 text-xs text-zinc-600 dark:text-zinc-400">{article.excerpt}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
