import { useEffect, useState } from 'react'
import { useStockMarketHours } from '../hooks/useStockMarketHours'
import type { StockMarketHoursItem } from '../types'

function sessionClass(session: string): string {
  const s = session.toLowerCase()
  if (s.includes('open')) return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
  if (s.includes('pre-market')) return 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
  if (s.includes('after-hours')) return 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300'
  return 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
}

function formatCountdown(isoString: string | null, _tick: number): string | null {
  if (!isoString) return null
  const diff = new Date(isoString).getTime() - Date.now()
  if (diff <= 0) return null
  const totalMinutes = Math.floor(diff / 60_000)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours > 0 && minutes > 0) return `${hours}h ${minutes}m`
  if (hours > 0) return `${hours}h`
  return `${minutes}m`
}

function ExchangeCard({ row, tick }: { row: StockMarketHoursItem; tick: number }) {
  const countdown = formatCountdown(row.next_close ?? row.next_open, tick)
  const label = row.next_close ? 'closes in' : 'opens in'
  const closureMessage =
    row.closure_reason === 'holiday'
      ? row.holiday_name
        ? `Holiday: ${row.holiday_name}`
        : 'Holiday closure'
      : row.closure_reason === 'weekend'
        ? 'Weekend closure'
        : null

  return (
    <article className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{row.exchange}</p>
          {countdown ? (
            <p className="text-[11px] text-zinc-500">
              {label} <span className="font-medium text-zinc-700 dark:text-zinc-300">{countdown}</span>
            </p>
          ) : (
            <p className="text-[11px] text-zinc-500">{row.timezone}</p>
          )}
          {closureMessage ? (
            <p className="text-[11px] font-medium text-amber-700 dark:text-amber-300">{closureMessage}</p>
          ) : null}
        </div>
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${sessionClass(row.session)}`}>
          {row.session}
        </span>
      </div>
    </article>
  )
}

export default function StockMarketHoursBanner() {
  const { data, loading, error } = useStockMarketHours()
  const [tick, setTick] = useState(0)

  // Re-render every minute so countdowns stay current
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 60_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Major Exchange Sessions</h2>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          Live
        </span>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-14 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load exchange session data.</p>
      ) : data.length === 0 ? (
        <p className="text-sm text-zinc-500">No exchange session data available right now.</p>
      ) : (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((row) => (
            <ExchangeCard key={row.exchange} row={row} tick={tick} />
          ))}
        </div>
      )}
    </div>
  )
}
