import { useMemo } from 'react'
import { useStockHalts } from '../hooks/useStockHalts'

export default function StockHaltsWidget() {
  const { data, loading, error } = useStockHalts()

  const rows = useMemo(() => data.slice(0, 12), [data])

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Nasdaq Trading Halts</h2>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          Today
        </span>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-8 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load stock halt data.</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-zinc-500">No Nasdaq halts recorded today.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs sm:text-sm">
            <thead className="border-b border-zinc-200 text-zinc-500 dark:border-zinc-800">
              <tr>
                <th className="py-2">Time</th>
                <th className="py-2">Symbol</th>
                <th className="py-2">Resumption</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => {
                const symbol = row['Issue Symbol'] || '?'
                const symbolHref = `https://www.nasdaq.com/market-activity/stocks/${symbol.toLowerCase()}`

                return (
                  <tr key={`${symbol}-${row.Time}-${idx}`} className="border-b border-zinc-100 dark:border-zinc-900/80">
                    <td className="py-2 font-mono text-zinc-600 dark:text-zinc-300">{row.Time || '?'}</td>
                    <td className="py-2 font-semibold">
                      <a href={symbolHref} target="_blank" rel="noreferrer" className="hover:underline">
                        {symbol}
                      </a>
                    </td>
                    <td className="py-2 font-mono text-zinc-500">{row['Resumption Time'] || '?'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
