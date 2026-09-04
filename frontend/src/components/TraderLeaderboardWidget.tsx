import { useState } from 'react'
import { useTraderLeaderboard } from '../hooks/useTraderLeaderboard'
import type { TraderCallHorizon } from '../types'
import { formatReturnPct, hitRateClass, returnClass } from '../utils/traderFormat'

const HORIZONS: { value: TraderCallHorizon; label: string }[] = [
  { value: 1, label: '1 day' },
  { value: 7, label: '7 days' },
  { value: 30, label: '30 days' },
]

export default function TraderLeaderboardWidget() {
  const [horizon, setHorizon] = useState<TraderCallHorizon>(7)
  const { data, loading, error } = useTraderLeaderboard(horizon)

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">
            Trader Credibility
          </h2>
          <p className="text-[10px] font-mono text-zinc-500">
            hit-rate of bullish/bearish calls, graded against price {horizon}d later
          </p>
        </div>

        <div
          role="tablist"
          aria-label="Grading horizon"
          className="inline-flex rounded-xl bg-zinc-100 p-1 dark:bg-zinc-900"
        >
          {HORIZONS.map(({ value, label }) => {
            const active = horizon === value
            return (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setHorizon(value)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                  active
                    ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-800 dark:text-zinc-100'
                    : 'text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'
                }`}
              >
                {label}
              </button>
            )
          })}
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-12 animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-900" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load the trader leaderboard.</p>
      ) : data.length === 0 ? (
        <p className="text-sm text-zinc-500">
          No traders have enough graded calls at this horizon yet.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-zinc-200 dark:border-zinc-800">
          <table className="w-full min-w-[420px] text-left text-sm">
            <thead className="bg-zinc-50 text-[10px] font-semibold uppercase tracking-wider text-zinc-500 dark:bg-zinc-900/70">
              <tr>
                <th className="px-3 py-2">#</th>
                <th className="px-3 py-2">Trader</th>
                <th className="px-3 py-2 text-right">Hit rate</th>
                <th className="px-3 py-2 text-right">Calls</th>
                <th className="px-3 py-2 text-right">Avg return</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
              {data.map((row, idx) => (
                <tr key={row.user_screen_name} className="bg-white dark:bg-zinc-900/40">
                  <td className="px-3 py-2 font-bold tabular-nums text-zinc-400">{idx + 1}</td>
                  <td className="px-3 py-2 font-semibold text-zinc-800 dark:text-zinc-100">
                    @{row.user_screen_name}
                  </td>
                  <td className={`px-3 py-2 text-right font-bold tabular-nums ${hitRateClass(row.hit_rate)}`}>
                    {Math.round(row.hit_rate * 100)}%
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-zinc-500 dark:text-zinc-400">
                    {row.graded_calls}
                  </td>
                  <td className={`px-3 py-2 text-right font-semibold tabular-nums ${returnClass(row.avg_return_pct)}`}>
                    {formatReturnPct(row.avg_return_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[11px] text-zinc-400 dark:text-zinc-500">
        A "call" is a non-neutral-sentiment tweet mentioning a ticker; "avg return" is what
        following the call would have made, signed for direction (bearish calls gain when price
        falls). Traders need at least 5 graded calls at a horizon to be ranked.
      </p>
    </div>
  )
}
