import { FormEvent, useEffect, useState } from 'react'
import { useAdvisor } from '../hooks/useAdvisor'
import type { AdvisorAction, AdvisorCall, AdvisorScoreBucket, AdvisorScorecard } from '../types'

const RULES_PLACEHOLDER = `For example:
- No single position above 20% of the portfolio.
- Take profit on a third of a position at +40%; review anything at -15%.
- Prefer large caps; no penny stocks, no leveraged ETFs.
- Medium risk appetite; I hold for weeks to months, not days.`

const ACTION_STYLES: Record<AdvisorAction, string> = {
  buy: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
  add: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400',
  trim: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
  sell: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300',
  watch: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300',
}

const card =
  'rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900'
const heading = 'text-sm font-semibold uppercase tracking-wider text-zinc-500'

function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

function pctTone(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'text-zinc-400'
  return value > 0 ? 'text-emerald-600 dark:text-emerald-400' : value < 0 ? 'text-red-500' : 'text-zinc-500'
}

function formatTime(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

/** What following the call made: a sell before a drop counts as a gain. */
function followedReturn(call: AdvisorCall, horizon: string): number | null {
  const result = call.results?.[horizon]
  if (!result || result.excluded) return null
  return call.action === 'trim' || call.action === 'sell' ? -result.return_pct : result.return_pct
}

function ScoreTile({ label, bucket }: { label: string; bucket: AdvisorScoreBucket | undefined }) {
  const graded = bucket?.graded ?? 0
  return (
    <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900/50">
      <div className="text-xs font-medium text-zinc-500">{label}</div>
      {graded === 0 ? (
        <div className="mt-1 text-sm text-zinc-500">Nothing graded yet</div>
      ) : (
        <div className="mt-1 flex items-baseline gap-3">
          <span className="text-2xl font-bold">{Math.round((bucket?.hit_rate ?? 0) * 100)}%</span>
          <span className={`text-sm font-semibold ${pctTone(bucket?.avg_return_pct)}`}>
            {formatPct(bucket?.avg_return_pct)} avg
          </span>
          <span className="text-xs text-zinc-500">{graded} graded</span>
        </div>
      )}
    </div>
  )
}

function Scorecard({ scorecard }: { scorecard: AdvisorScorecard | null }) {
  return (
    <section className={card}>
      <h2 className={heading}>Scorecard</h2>
      <p className="mt-1 text-xs text-zinc-500">
        Hit rate and average return of following Claude&apos;s buy, add, trim and sell calls.
        {scorecard ? ` ${scorecard.total_calls} call${scorecard.total_calls === 1 ? '' : 's'} logged.` : ''}
      </p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <ScoreTile label="After 7 days" bucket={scorecard?.horizons?.['7']} />
        <ScoreTile label="After 30 days" bucket={scorecard?.horizons?.['30']} />
      </div>
    </section>
  )
}

function StrategyForm({
  rules,
  watchlist,
  updatedAt,
  onSave,
}: {
  rules: string
  watchlist: string[]
  updatedAt: string | null
  onSave: (rules: string, watchlist: string[]) => Promise<unknown>
}) {
  const [draftRules, setDraftRules] = useState(rules)
  const [draftWatchlist, setDraftWatchlist] = useState(watchlist.join(', '))
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')

  useEffect(() => setDraftRules(rules), [rules])
  useEffect(() => setDraftWatchlist(watchlist.join(', ')), [watchlist])

  const onSubmit = async (ev: FormEvent<HTMLFormElement>) => {
    ev.preventDefault()
    setStatus('saving')
    try {
      const symbols = draftWatchlist
        .split(/[\s,]+/)
        .map((s) => s.trim())
        .filter(Boolean)
      await onSave(draftRules, symbols)
      setStatus('saved')
    } catch {
      setStatus('error')
    }
  }

  return (
    <section className={card}>
      <h2 className={heading}>Your strategy</h2>
      <p className="mt-1 text-xs text-zinc-500">
        Claude reads these rules on every market check and names the rule behind each suggestion. Only you can
        change them.
      </p>
      <form className="mt-3 grid gap-3" onSubmit={onSubmit}>
        <label className="grid gap-1 text-xs font-medium text-zinc-500">
          Rules
          <textarea
            value={draftRules}
            onChange={(ev) => setDraftRules(ev.target.value)}
            placeholder={RULES_PLACEHOLDER}
            rows={7}
            aria-label="Strategy rules"
            className="rounded-lg border border-zinc-300 bg-white px-2.5 py-2 font-mono text-sm text-zinc-900 outline-none ring-zinc-400 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
        </label>
        <label className="grid gap-1 text-xs font-medium text-zinc-500">
          Watchlist
          <input
            value={draftWatchlist}
            onChange={(ev) => setDraftWatchlist(ev.target.value)}
            placeholder="NVDA, AMD, PLTR"
            aria-label="Watchlist"
            className="rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm text-zinc-900 outline-none ring-zinc-400 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={status === 'saving'}
            className="rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            {status === 'saving' ? 'Saving...' : 'Save strategy'}
          </button>
          {status === 'saved' && <span className="text-xs text-emerald-600 dark:text-emerald-400">Saved</span>}
          {status === 'error' && (
            <span className="text-xs text-red-500" role="alert">
              Couldn&apos;t save the strategy.
            </span>
          )}
          {updatedAt && status !== 'saved' && (
            <span className="text-xs text-zinc-500">Last changed {formatTime(updatedAt)}</span>
          )}
        </div>
      </form>
    </section>
  )
}

function Journal({ calls, onTickerClick }: { calls: AdvisorCall[]; onTickerClick?: (ticker: string) => void }) {
  return (
    <section className={card}>
      <h2 className={heading}>Decision journal</h2>
      <p className="mt-1 text-xs text-zinc-500">
        Every suggestion Claude made during a market check, priced when it was made and graded after 7 and 30 days.
      </p>
      {calls.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-500">
          No calls yet. They appear here once the scheduled market check starts running.
        </p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wider text-zinc-500">
              <tr>
                <th className="py-2 pr-3 font-medium">When</th>
                <th className="py-2 pr-3 font-medium">Call</th>
                <th className="py-2 pr-3 text-right font-medium">Price</th>
                <th className="py-2 pr-3 text-right font-medium">7d</th>
                <th className="py-2 pr-3 text-right font-medium">30d</th>
                <th className="py-2 font-medium">Why</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {calls.map((call) => {
                const seven = followedReturn(call, '7')
                const thirty = followedReturn(call, '30')
                return (
                  <tr key={call.id} className="align-top">
                    <td className="whitespace-nowrap py-2 pr-3 text-xs text-zinc-500">{formatTime(call.called_at)}</td>
                    <td className="whitespace-nowrap py-2 pr-3">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase ${ACTION_STYLES[call.action] ?? ACTION_STYLES.watch}`}
                      >
                        {call.action}
                      </span>{' '}
                      <button
                        type="button"
                        onClick={() => onTickerClick?.(call.symbol)}
                        className="font-semibold hover:underline"
                      >
                        {call.symbol}
                      </button>
                      {call.conviction && <div className="mt-0.5 text-[11px] text-zinc-500">{call.conviction} conviction</div>}
                    </td>
                    <td className="whitespace-nowrap py-2 pr-3 text-right tabular-nums">
                      {call.price_at_call != null ? call.price_at_call.toFixed(2) : '—'}
                    </td>
                    <td className={`whitespace-nowrap py-2 pr-3 text-right tabular-nums ${pctTone(seven)}`}>
                      {call.action === 'watch' ? '' : formatPct(seven)}
                    </td>
                    <td className={`whitespace-nowrap py-2 pr-3 text-right tabular-nums ${pctTone(thirty)}`}>
                      {call.action === 'watch' ? '' : formatPct(thirty)}
                    </td>
                    <td className="py-2 text-xs text-zinc-600 dark:text-zinc-300">
                      {call.reasoning}
                      {call.rule && <div className="mt-0.5 text-[11px] text-zinc-500">Rule: {call.rule}</div>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default function AdvisorPanel({ onTickerClick }: { onTickerClick?: (ticker: string) => void }) {
  const { strategy, calls, scorecard, loading, error, saveStrategy } = useAdvisor()

  if (loading) {
    return <section className={`${card} h-40 animate-pulse`} aria-label="Loading advisor" />
  }
  if (error) {
    return (
      <section className={card}>
        <p className="text-sm text-red-500">Failed to load the market check data.</p>
      </section>
    )
  }

  return (
    <>
      <Scorecard scorecard={scorecard} />
      <Journal calls={calls} onTickerClick={onTickerClick} />
      <StrategyForm
        rules={strategy.rules}
        watchlist={strategy.watchlist}
        updatedAt={strategy.updated_at}
        onSave={saveStrategy}
      />
    </>
  )
}
