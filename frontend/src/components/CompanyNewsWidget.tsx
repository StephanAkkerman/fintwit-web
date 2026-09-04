import { useState } from 'react'
import { useCompanyNews } from '../hooks/useCompanyNews'

function fmtDate(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

export default function CompanyNewsWidget() {
  const [symbolInput, setSymbolInput] = useState('AAPL')
  const [symbol, setSymbol] = useState('AAPL')
  const { data, loading, error } = useCompanyNews(symbol)

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
        <ul className="space-y-3">
          {data.articles.map((article) => (
            <li key={article.url} className="border-b border-zinc-100 pb-3 last:border-0 last:pb-0 dark:border-zinc-900/80">
              <a
                href={article.url}
                target="_blank"
                rel="noreferrer"
                className="text-sm font-semibold text-zinc-900 hover:underline dark:text-zinc-100"
              >
                {article.title}
              </a>
              <p className="mt-0.5 text-[11px] text-zinc-500">
                {article.source ?? 'Unknown source'} &middot; {fmtDate(article.date)}
              </p>
              {article.excerpt && (
                <p className="mt-1 line-clamp-2 text-xs text-zinc-600 dark:text-zinc-400">{article.excerpt}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
