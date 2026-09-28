import { useEffect, useState } from 'react'
import { useTraderLeaderboard } from '../hooks/useTraderLeaderboard'
import type { TraderCallHorizon } from '../types'
import { formatReturnPct, hitRateClass, returnClass, traderFromPath } from '../utils/traderFormat'
import TraderDetailPanel from './TraderDetailPanel'

const HORIZONS: { value: TraderCallHorizon; label: string }[] = [
  { value: 1, label: '1 day' },
  { value: 7, label: '7 days' },
  { value: 30, label: '30 days' },
]

type Props = {
  onTickerClick?: (ticker: string) => void
}

export default function TraderLeaderboardWidget({ onTickerClick }: Props) {
  const [horizon, setHorizon] = useState<TraderCallHorizon>(7)
  const { data, loading, error } = useTraderLeaderboard(horizon)
  // `/traders/<handle>` deep-links straight to a trader's calls.
  const [selected, setSelected] = useState<string | null>(() => traderFromPath(window.location.pathname))
  const [lookupInput, setLookupInput] = useState('')

  useEffect(() => {
    const onPopState = () => setSelected(traderFromPath(window.location.pathname))
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const openTrader = (screenName: string | null) => {
    setSelected(screenName)
    const path = screenName ? `/traders/${encodeURIComponent(screenName)}` : '/traders'
    if (window.location.pathname !== path) window.history.pushState({}, '', path)
  }

  // Clicking the open trader's row again collapses the panel.
  const toggleTrader = (screenName: string) =>
    openTrader(screenName.toLowerCase() === selected?.toLowerCase() ? null : screenName)

  const submitLookup = () => {
    const handle = lookupInput.trim().replace(/^@/, '')
    if (!handle) return
    openTrader(handle)
    setLookupInput('')
  }

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

        <div className="flex flex-wrap items-center gap-2">
          <form
            className="flex items-center gap-1"
            onSubmit={(e) => {
              e.preventDefault()
              submitLookup()
            }}
          >
            <input
              value={lookupInput}
              onChange={(e) => setLookupInput(e.target.value)}
              placeholder="@any trader"
              aria-label="Look up a trader"
              className="w-32 rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-xs text-zinc-800 placeholder:text-zinc-400 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-100"
            />
            <button
              type="submit"
              className="rounded-lg bg-zinc-100 px-2.5 py-1.5 text-xs font-semibold text-zinc-600 hover:text-zinc-900 dark:bg-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
            >
              View
            </button>
          </form>

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
              {data.map((row, idx) => {
                const active = row.user_screen_name.toLowerCase() === selected?.toLowerCase()
                return (
                  <tr
                    key={row.user_screen_name}
                    onClick={() => toggleTrader(row.user_screen_name)}
                    className={`cursor-pointer transition-colors ${
                      active
                        ? 'bg-zinc-100 dark:bg-zinc-800/80'
                        : 'bg-white hover:bg-zinc-50 dark:bg-zinc-900/40 dark:hover:bg-zinc-900'
                    }`}
                  >
                    <td className="px-3 py-2 font-bold tabular-nums text-zinc-400">{idx + 1}</td>
                    <td className="px-3 py-2 font-semibold text-zinc-800 dark:text-zinc-100">
                      {/* The row is clickable for the mouse; this button is the keyboard/AT path. */}
                      <button
                        type="button"
                        aria-expanded={active}
                        onClick={(e) => {
                          e.stopPropagation()
                          toggleTrader(row.user_screen_name)
                        }}
                        className="hover:underline"
                      >
                        @{row.user_screen_name}
                      </button>
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
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <TraderDetailPanel
          key={selected}
          screenName={selected}
          horizon={horizon}
          onClose={() => openTrader(null)}
          onTickerClick={onTickerClick}
        />
      )}

      <p className="text-[11px] text-zinc-400 dark:text-zinc-500">
        A "call" is a non-neutral-sentiment tweet mentioning a ticker; "avg return" is what
        following the call would have made, signed for direction (bearish calls gain when price
        falls). Traders need at least 5 graded calls at a horizon to be ranked; click one to see
        their calls, or look up any handle. A move over +1000% is treated as a pricing mismatch
        (the ticker re-priced as a different asset) and left out of every score.
      </p>
    </div>
  )
}
