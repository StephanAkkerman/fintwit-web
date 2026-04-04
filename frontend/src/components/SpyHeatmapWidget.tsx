import { useMemo, useState } from 'react';
import { useSpyHeatmap } from '../hooks/useSpyHeatmap';
import type { SpyHeatmapDateRange } from '../types';

const RANGE_OPTIONS: Array<{ key: SpyHeatmapDateRange; label: string }> = [
  { key: 'one_day', label: '1D' },
  { key: 'one_week', label: '1W' },
  { key: 'one_month', label: '1M' },
  { key: 'ytd', label: 'YTD' },
  { key: 'one_year', label: '1Y' },
]

function toNumber(value: string | number | null | undefined): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function formatMarketCap(value: number): string {
  if (value >= 1_000_000_000_000) return `$${(value / 1_000_000_000_000).toFixed(2)}T`
  if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  return `$${Math.round(value).toLocaleString()}`
}

function toneClass(changePercent: number | null): string {
  if (changePercent === null) {
    return 'border-zinc-200 bg-zinc-100 text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300'
  }
  if (changePercent >= 2) {
    return 'border-emerald-400/50 bg-emerald-400/25 text-emerald-900 dark:text-emerald-100'
  }
  if (changePercent > 0) {
    return 'border-emerald-300/50 bg-emerald-300/20 text-emerald-900 dark:text-emerald-100'
  }
  if (changePercent <= -2) {
    return 'border-rose-400/50 bg-rose-400/25 text-rose-900 dark:text-rose-100'
  }
  return 'border-rose-300/50 bg-rose-300/20 text-rose-900 dark:text-rose-100'
}

export default function SpyHeatmapWidget() {
  const [range, setRange] = useState<SpyHeatmapDateRange>('one_day')
  const { data, loading, error } = useSpyHeatmap(range)

  const cells = useMemo(() => {
    return data
      .map((row) => {
        const close = toNumber(row.close)
        const prevClose = toNumber(row.prev_close)
        const marketCap = toNumber(row.marketcap) ?? 0

        let changePercent: number | null = null
        if (close !== null && prevClose !== null && prevClose !== 0) {
          changePercent = ((close - prevClose) / prevClose) * 100
        }

        return {
          ticker: row.ticker,
          sector: row.sector ?? 'Unknown',
          marketCap,
          changePercent,
        }
      })
      .filter((row) => Boolean(row.ticker))
      .sort((a, b) => b.marketCap - a.marketCap)
      .slice(0, 24)
  }, [data])

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">SPY Heatmap</h2>
          <p className="text-xs text-zinc-500">Top S&P 500 names by market cap</p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {RANGE_OPTIONS.map((option) => {
            const active = option.key === range
            return (
              <button
                key={option.key}
                type="button"
                onClick={() => setRange(option.key)}
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
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
          {Array.from({ length: 12 }).map((_, idx) => (
            <div key={idx} className="h-16 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load SPY heatmap data.</p>
      ) : cells.length === 0 ? (
        <p className="text-sm text-zinc-500">No heatmap data available right now.</p>
      ) : (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
          {cells.map((cell) => (
            <div
              key={`${cell.ticker}-${cell.sector}`}
              className={`rounded-lg border p-2 ${toneClass(cell.changePercent)}`}
              title={cell.sector}
            >
              <div className="text-sm font-semibold">{cell.ticker}</div>
              <div className="text-[11px] opacity-80">{cell.sector}</div>
              <div className="mt-1 text-xs font-mono">
                {cell.changePercent === null
                  ? 'N/A'
                  : `${cell.changePercent >= 0 ? '+' : ''}${cell.changePercent.toFixed(2)}%`}
              </div>
              <div className="text-[11px] opacity-80">{formatMarketCap(cell.marketCap)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
