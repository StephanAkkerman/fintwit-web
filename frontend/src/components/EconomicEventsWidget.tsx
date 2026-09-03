import { useMemo } from 'react'
import { useEconomicEvents } from '../hooks/useEconomicEvents'

function zoneFlag(zone: string | null): string {
  if (!zone) return '🌐'
  if (zone === 'united states') return '🇺🇸'
  if (zone === 'euro zone') return '🇪🇺'
  return '🌐'
}

function trimField(value: string | null): string {
  const normalized = (value ?? '').trim()
  return normalized || '~'
}

function resolveImpactEmoji(impactEmoji: string | null, impactScore: number | null): string {
  if (impactEmoji) return impactEmoji
  if (impactScore === 3) return '🟥'
  if (impactScore === 2) return '🟧'
  if (impactScore === 1) return '🟨'
  return '⬜'
}

export default function EconomicEventsWidget() {
  const { data, loading, error } = useEconomicEvents(12)

  const rows = useMemo(() => data.slice(0, 8), [data])

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">
          Economic Events
        </h2>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          Investing
        </span>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, idx) => (
            <div key={idx} className="h-10 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load economic events.</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-zinc-500">No economic events available right now.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs sm:text-sm">
            <thead className="border-b border-zinc-200 text-zinc-500 dark:border-zinc-800">
              <tr>
                <th className="py-2">Date</th>
                <th className="py-2">Event</th>
                <th className="py-2 text-center">Impact</th>
                <th className="py-2 text-right">A | F | P</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const dateLabel = [row.date, row.time]
                  .filter((value): value is string => Boolean(value && value.trim()))
                  .join(' ')
                const metricLabel = `${trimField(row.actual)} | ${trimField(row.forecast)} | ${trimField(row.previous)}`
                const impactLabel = resolveImpactEmoji(row.impact_emoji, row.impact_score)

                return (
                  <tr
                    key={`${row.id}-${row.event}`}
                    className="border-b border-zinc-100 dark:border-zinc-900/80"
                  >
                    <td className="py-2 align-top text-zinc-500">{dateLabel || 'TBD'}</td>
                    <td className="py-2 align-top">
                      <p className="font-semibold text-zinc-900 dark:text-zinc-100">{row.event}</p>
                      <p className="text-[11px] uppercase tracking-wide text-zinc-500">
                        {zoneFlag(row.zone)}
                      </p>
                    </td>
                    <td className="py-2 text-center text-base leading-none">{impactLabel}</td>
                    <td className="py-2 text-right font-mono text-[11px] text-zinc-500">{metricLabel}</td>
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
