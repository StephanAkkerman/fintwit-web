import { useMemo } from 'react'
import { useEarningsCalendar } from '../hooks/useEarningsCalendar'
import type { EarningsRow } from '../types'
import type { PortfolioTickerLookup } from '../hooks/usePortfolioTickers'
import { PortfolioTickerBadge } from './PortfolioTickerBadge'

const ROWS_PER_DAY = 6

function weekdayLabel(dateStr: string): string {
  const d = new Date(`${dateStr}T00:00:00Z`)
  if (Number.isNaN(d.getTime())) return dateStr
  return d.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

function formatMarketCap(value: number | null): string | null {
  if (value === null) return null
  if (value >= 1e12) return `$${(value / 1e12).toFixed(1)}T`
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`
  if (value >= 1e6) return `$${(value / 1e6).toFixed(0)}M`
  return `$${value.toFixed(0)}`
}

function formatEps(value: number | null): string | null {
  if (value === null) return null
  return `${value >= 0 ? '' : '-'}$${Math.abs(value).toFixed(2)} est.`
}

interface RowProps {
  row: EarningsRow
  portfolioLookup?: PortfolioTickerLookup
}

function EarningsRowItem({ row, portfolioLookup }: RowProps) {
  const marketCapLabel = formatMarketCap(row.market_cap)
  const epsLabel = formatEps(row.eps_forecast)

  return (
    <li className="flex items-center justify-between gap-2 py-1 text-xs">
      <a
        href={row.website ?? undefined}
        target="_blank"
        rel="noreferrer"
        title={row.name ?? row.symbol}
        className="flex min-w-0 items-center gap-1 font-semibold text-zinc-800 hover:underline dark:text-zinc-100"
      >
        <span className="truncate">{row.symbol}</span>
        <PortfolioTickerBadge status={portfolioLookup?.(row.symbol) ?? null} />
      </a>
      <span className="flex shrink-0 items-center gap-1 font-mono text-[11px] text-zinc-500 dark:text-zinc-400">
        {row.session_emoji ?? ''}
        {epsLabel ?? marketCapLabel ?? ''}
      </span>
    </li>
  )
}

interface Props {
  days?: number
  portfolioLookup?: PortfolioTickerLookup
}

export default function EarningsCalendarWidget({ days = 7, portfolioLookup }: Props) {
  const { data, loading, error } = useEarningsCalendar(days)

  const totalReporting = useMemo(
    () => data.days.reduce((sum, day) => sum + day.count, 0),
    [data.days]
  )

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">
          Earnings Calendar
        </h2>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          Next {days}d{totalReporting > 0 ? ` · ${totalReporting} reporting` : ''}
        </span>
      </div>

      {loading ? (
        <div className="flex gap-3 overflow-hidden">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-40 w-48 shrink-0 animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load the earnings calendar.</p>
      ) : data.days.length === 0 ? (
        <p className="text-sm text-zinc-500">No earnings calendar data available right now.</p>
      ) : (
        <div className="overflow-x-auto">
          <div className="flex min-w-max gap-3">
            {data.days.map((day) => (
              <div
                key={day.date}
                className="w-48 shrink-0 rounded-xl border border-zinc-100 bg-zinc-50/60 p-3 dark:border-zinc-800 dark:bg-zinc-950/40"
              >
                <div className="mb-2 flex items-center justify-between gap-1">
                  <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-200">
                    {weekdayLabel(day.date)}
                  </span>
                  {day.count > 0 && (
                    <span className="text-[10px] text-zinc-500">{day.count}</span>
                  )}
                </div>
                {day.rows.length === 0 ? (
                  <p className="text-[11px] text-zinc-500">No major earnings</p>
                ) : (
                  <ul className="divide-y divide-zinc-100 dark:divide-zinc-900">
                    {day.rows.slice(0, ROWS_PER_DAY).map((row) => (
                      <EarningsRowItem key={row.symbol} row={row} portfolioLookup={portfolioLookup} />
                    ))}
                  </ul>
                )}
                {day.rows.length > ROWS_PER_DAY && (
                  <p className="mt-1 font-mono text-[10px] text-zinc-500">
                    +{day.rows.length - ROWS_PER_DAY} more
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
