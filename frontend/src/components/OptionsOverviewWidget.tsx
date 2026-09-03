import { useMemo } from 'react'
import { useOptionsOverview } from '../hooks/useOptionsOverview'

function fmtInt(value: number): string {
  return value.toLocaleString()
}

function fmtRatio(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return 'N/A'
  return value.toFixed(2)
}

export default function OptionsOverviewWidget() {
  const { data, loading, error } = useOptionsOverview()

  const topContracts = useMemo(() => data.most_active_contracts.slice(0, 8), [data.most_active_contracts])

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Options Overview</h2>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          {data.source.toUpperCase()}
        </span>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-8 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load options overview.</p>
      ) : (
        <>
          <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
            <article className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">Calls</p>
              <p className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{fmtInt(data.totals.call_volume)}</p>
            </article>
            <article className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">Puts</p>
              <p className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{fmtInt(data.totals.put_volume)}</p>
            </article>
            <article className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">Put/Call Ratio</p>
              <p className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{fmtRatio(data.totals.put_call_ratio)}</p>
            </article>
          </div>

          {topContracts.length === 0 ? (
            <p className="text-sm text-zinc-500">No options activity data available right now.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs sm:text-sm">
                <thead className="border-b border-zinc-200 text-zinc-500 dark:border-zinc-800">
                  <tr>
                    <th className="py-2">Symbol</th>
                    <th className="py-2">Type</th>
                    <th className="py-2">Expiry</th>
                    <th className="py-2 text-right">Strike</th>
                    <th className="py-2 text-right">Volume</th>
                    <th className="py-2 text-right">OI</th>
                  </tr>
                </thead>
                <tbody>
                  {topContracts.map((row) => (
                    <tr
                      key={`${row.symbol}-${row.contract_type}-${row.expiry_date}-${row.strike}`}
                      className="border-b border-zinc-100 dark:border-zinc-900/80"
                    >
                      <td className="py-2 font-semibold">
                        {row.website ? (
                          <a href={row.website} target="_blank" rel="noreferrer" className="hover:underline">
                            {row.symbol}
                          </a>
                        ) : (
                          row.symbol
                        )}
                      </td>
                      <td className="py-2">
                        <span
                          className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                            row.contract_type === 'CALL'
                              ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
                              : 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
                          }`}
                        >
                          {row.contract_type}
                        </span>
                      </td>
                      <td className="py-2 text-zinc-600 dark:text-zinc-300">{row.expiry_date ?? 'N/A'}</td>
                      <td className="py-2 text-right font-mono">{row.strike?.toFixed(2) ?? 'N/A'}</td>
                      <td className="py-2 text-right font-mono">{fmtInt(row.volume)}</td>
                      <td className="py-2 text-right font-mono text-zinc-500">{fmtInt(row.open_interest)}</td>
                    </tr>
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
