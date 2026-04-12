import { useMemo } from 'react'
import { useBinanceGainersLosers } from '../hooks/useBinanceGainersLosers'
import type { BinanceMoverItem } from '../types'

function formatPrice(value: number): string {
  return `$${value.toLocaleString(undefined, {
    minimumFractionDigits: value < 1 ? 4 : 2,
    maximumFractionDigits: value < 1 ? 4 : 2,
  })}`
}

function MoverRows({ rows }: { rows: BinanceMoverItem[] }) {
  if (rows.length === 0) {
    return <p className="text-xs text-zinc-500">No symbols available.</p>
  }

  return (
    <div className="space-y-1.5">
      {rows.map((row) => {
        const changeClass =
          row.price_change_percent > 0
            ? 'text-emerald-600 dark:text-emerald-400'
            : row.price_change_percent < 0
              ? 'text-rose-600 dark:text-rose-400'
              : 'text-zinc-500 dark:text-zinc-400'

        return (
          <article
            key={`${row.symbol}-${row.price_change_percent}`}
            className="flex items-center justify-between rounded-lg border border-zinc-200 bg-zinc-50 px-2.5 py-2 dark:border-zinc-800 dark:bg-zinc-900/60"
          >
            <div className="min-w-0">
              <a
                href={row.website}
                target="_blank"
                rel="noreferrer"
                className="text-sm font-semibold hover:underline"
              >
                {row.symbol}
              </a>
              <p className="text-[11px] text-zinc-500">{formatPrice(row.price)}</p>
            </div>
            <p className={`font-mono text-sm font-semibold ${changeClass}`}>
              {row.price_change_percent > 0 ? '+' : ''}
              {row.price_change_percent.toFixed(2)}%
            </p>
          </article>
        )
      })}
    </div>
  )
}

export default function BinanceGainersLosersWidget() {
  const { data, loading, error } = useBinanceGainersLosers()

  const gainers = useMemo(() => data.gainers.slice(0, 5), [data.gainers])
  const losers = useMemo(() => data.losers.slice(0, 5), [data.losers])

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Binance Movers</h2>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          24h
        </span>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-9 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load Binance movers.</p>
      ) : gainers.length === 0 && losers.length === 0 ? (
        <p className="text-sm text-zinc-500">No Binance mover data available right now.</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-emerald-600 dark:text-emerald-400">
              Top Gainers
            </h3>
            <MoverRows rows={gainers} />
          </section>
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-rose-600 dark:text-rose-400">
              Top Losers
            </h3>
            <MoverRows rows={losers} />
          </section>
        </div>
      )}
    </div>
  )
}
