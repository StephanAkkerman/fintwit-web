import { useMemo, useState } from 'react'
import { useEarningsResults } from '../hooks/useEarningsResults'
import type { EarningsOutcome, EarningsResult } from '../types'
import type { PortfolioTickerLookup } from '../hooks/usePortfolioTickers'
import { PortfolioTickerBadge } from './PortfolioTickerBadge'

const BADGE_BASE = 'rounded-full px-2 py-0.5 text-[11px] font-semibold'

const OUTCOME: Record<EarningsOutcome, { label: string; className: string }> = {
  beat: { label: 'Beat', className: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300' },
  miss: { label: 'Miss', className: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300' },
  inline: { label: 'In line', className: 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300' },
}

type Filter = 'all' | 'beat' | 'miss'

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'beat', label: 'Beats' },
  { key: 'miss', label: 'Misses' },
]

const MAX_ROWS = 15

export function formatEpsValue(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${value < 0 ? '-' : ''}$${Math.abs(value).toFixed(2)}`
}

export function surpriseClass(value: number | null | undefined): string {
  if (value == null) return 'text-zinc-500'
  if (value > 0) return 'text-emerald-600 dark:text-emerald-400'
  if (value < 0) return 'text-rose-600 dark:text-rose-400'
  return 'text-zinc-500'
}

function formatSurprise(value: number | null): string {
  if (value == null) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

function dayLabel(dateStr: string): string {
  const d = new Date(`${dateStr}T00:00:00Z`)
  if (Number.isNaN(d.getTime())) return dateStr
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' })
}

function ResultRow({ row, portfolioLookup }: { row: EarningsResult; portfolioLookup?: PortfolioTickerLookup }) {
  const outcome = row.outcome ? OUTCOME[row.outcome] : null
  return (
    <tr className="border-b border-zinc-100 dark:border-zinc-900/80">
      <td className="py-2">
        <a
          href={row.website ?? undefined}
          target="_blank"
          rel="noreferrer"
          title={row.name ?? row.symbol}
          className="flex items-center gap-1 font-semibold text-zinc-800 hover:underline dark:text-zinc-100"
        >
          {row.symbol}
          <PortfolioTickerBadge status={portfolioLookup?.(row.symbol) ?? null} />
        </a>
        {row.name && <p className="max-w-[14rem] truncate text-[11px] text-zinc-500">{row.name}</p>}
      </td>
      <td className="py-2 text-zinc-600 dark:text-zinc-300">
        {dayLabel(row.date)} {row.session_emoji ?? ''}
      </td>
      <td className="py-2 text-right font-mono">
        {formatEpsValue(row.eps_actual)}
        <span className="text-zinc-500"> / {formatEpsValue(row.eps_forecast)}</span>
      </td>
      <td className={`py-2 text-right font-mono ${surpriseClass(row.surprise_pct)}`}>
        {formatSurprise(row.surprise_pct)}
      </td>
      <td className="py-2 text-right">
        {outcome && <span className={`${BADGE_BASE} ${outcome.className}`}>{outcome.label}</span>}
      </td>
    </tr>
  )
}

interface Props {
  days?: number
  portfolioLookup?: PortfolioTickerLookup
}

export default function EarningsResultsWidget({ days = 5, portfolioLookup }: Props) {
  const { data, loading, error } = useEarningsResults(days)
  const [filter, setFilter] = useState<Filter>('all')

  const rows = useMemo(
    () => data.results.filter((row) => filter === 'all' || row.outcome === filter).slice(0, MAX_ROWS),
    [data.results, filter],
  )
  const { reported, beat } = data.summary
  const graded = data.summary.beat + data.summary.miss + data.summary.inline

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Earnings Results</h2>
        <div className="flex flex-wrap items-center gap-2">
          {graded > 0 && (
            <span className="text-[11px] text-zinc-500">
              {beat} of {graded} beat ({Math.round((beat / graded) * 100)}%)
            </span>
          )}
          <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
            Last {days} trading days{reported > 0 ? ` · ${reported} reported` : ''}
          </span>
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-8 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load earnings results.</p>
      ) : data.results.length === 0 ? (
        <p className="text-sm text-zinc-500">No companies have reported in this window yet.</p>
      ) : (
        <>
          <div className="mb-2 flex gap-1" role="group" aria-label="Filter results">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => setFilter(f.key)}
                aria-pressed={filter === f.key}
                className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                  filter === f.key
                    ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                    : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
          {rows.length === 0 ? (
            <p className="text-sm text-zinc-500">Nothing matches this filter.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs sm:text-sm">
                <thead className="border-b border-zinc-200 text-zinc-500 dark:border-zinc-800">
                  <tr>
                    <th className="py-2">Company</th>
                    <th className="py-2">Reported</th>
                    <th className="py-2 text-right">EPS / est.</th>
                    <th className="py-2 text-right">Surprise</th>
                    <th className="py-2 text-right">Result</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <ResultRow key={`${row.symbol}-${row.date}`} row={row} portfolioLookup={portfolioLookup} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
