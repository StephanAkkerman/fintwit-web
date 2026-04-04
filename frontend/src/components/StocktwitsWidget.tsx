import { useState } from 'react';
import { useStocktwits } from '../hooks/useStocktwits';
import type { StocktwitsKeyword } from '../types';

const KEYWORD_OPTIONS: Array<{ key: StocktwitsKeyword; label: string }> = [
  { key: 'ts', label: 'Trending' },
  { key: 'm_day', label: 'Most Active' },
  { key: 'wl_ct_day', label: 'Most Watched' },
]

export default function StocktwitsWidget() {
  const [keyword, setKeyword] = useState<StocktwitsKeyword>('ts')
  const { data, loading, error } = useStocktwits(keyword)

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">
          StockTwits Signals
        </h2>
        <div className="flex flex-wrap gap-1.5">
          {KEYWORD_OPTIONS.map((option) => {
            const active = option.key === keyword
            return (
              <button
                key={option.key}
                type="button"
                onClick={() => setKeyword(option.key)}
                className={`rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                  active
                    ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                    : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
                }`}
              >
                {option.label}
              </button>
            )
          })}
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-8 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load StockTwits data.</p>
      ) : data.length === 0 ? (
        <p className="text-sm text-zinc-500">No StockTwits data available right now.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs sm:text-sm">
            <thead className="border-b border-zinc-200 text-zinc-500 dark:border-zinc-800">
              <tr>
                <th className="py-2">Symbol</th>
                <th className="py-2">Name</th>
                <th className="py-2 text-right">Rank Value</th>
                <th className="py-2 text-right">Price</th>
              </tr>
            </thead>
            <tbody>
              {data.slice(0, 8).map((row) => (
                <tr key={`${row.stock_id ?? row.symbol}-${row.symbol}`} className="border-b border-zinc-100 dark:border-zinc-900/80">
                  <td className="py-2 font-semibold">
                    <a
                      href={`https://stocktwits.com/symbol/${row.symbol}`}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:underline"
                    >
                      ${row.symbol}
                    </a>
                  </td>
                  <td className="max-w-[12rem] truncate py-2 text-zinc-600 dark:text-zinc-300">
                    {row.name}
                  </td>
                  <td className="py-2 text-right font-mono text-zinc-500">{row.val}</td>
                  <td className="py-2 text-right font-mono">{row.price}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
