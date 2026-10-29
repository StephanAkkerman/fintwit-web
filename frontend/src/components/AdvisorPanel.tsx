import { FormEvent, useEffect, useState } from 'react'
import { useAdvisor } from '../hooks/useAdvisor'
import type {
  AdvisorAction,
  AdvisorCall,
  AdvisorFeedMarket,
  AdvisorRun,
  AdvisorScoreBucket,
  AdvisorScorecard,
  AdvisorStrategy,
  AdvisorStrategyDraft,
  PaperPortfolio,
} from '../types'

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

const CURRENCIES = ['USD', 'EUR', 'GBP', 'CHF', 'CAD', 'AUD', 'JPY']

const inputClass =
  'rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm text-zinc-900 outline-none ring-zinc-400 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100'

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

function formatRate(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${Math.round(value * 100)}%`
}

function hitRate(bucket: AdvisorScoreBucket | undefined): string {
  return bucket && bucket.graded > 0 ? `${formatRate(bucket.hit_rate)} of ${bucket.graded}` : '—'
}

function PaperPositions({
  portfolio,
  onTickerClick,
}: {
  portfolio: PaperPortfolio
  onTickerClick?: (ticker: string) => void
}) {
  return (
    <div className="mt-2 grid gap-2 text-xs text-zinc-600 dark:text-zinc-300">
      <p>
        <span className="font-semibold text-zinc-500">Buy: </span>
        {portfolio.entry}
      </p>
      <p>
        <span className="font-semibold text-zinc-500">Sell: </span>
        {portfolio.exit}
      </p>
      {portfolio.positions.length === 0 ? (
        <p className="text-zinc-500">No paper trades yet.</p>
      ) : (
        <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {portfolio.positions.map((position) => (
            <li key={position.entry_call_id} className="flex flex-wrap items-baseline gap-x-3 py-1.5">
              <button
                type="button"
                onClick={() => onTickerClick?.(position.symbol)}
                className="w-14 font-semibold text-zinc-900 hover:underline dark:text-zinc-100"
              >
                {position.symbol}
              </button>
              <span className="tabular-nums">
                {position.entry_price.toFixed(2)} →{' '}
                {(position.status === 'open' ? position.price_now : position.exit_price)?.toFixed(2) ?? '—'}
              </span>
              <span className={`font-semibold tabular-nums ${pctTone(position.return_pct)}`}>
                {formatPct(position.return_pct)}
              </span>
              <span className="text-zinc-500">
                {position.status === 'open' ? 'open' : position.exit_reason === 'sell' ? 'sold' : position.exit_reason}
                {position.days_held != null && `, ${position.days_held}d`}
              </span>
              <span className="ml-auto text-zinc-500">{formatTime(position.entered_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function PaperStrategies({
  portfolios,
  onTickerClick,
}: {
  portfolios: PaperPortfolio[]
  onTickerClick?: (ticker: string) => void
}) {
  if (portfolios.length === 0) return null
  const ranked = [...portfolios].sort((a, b) => (b.avg_return_pct ?? -Infinity) - (a.avg_return_pct ?? -Infinity))
  return (
    <section className={card}>
      <h2 className={heading}>Paper strategies</h2>
      <p className="mt-1 text-xs text-zinc-500">
        Rule-based strategies Claude trades on paper during each check, with the same money in every position. None of
        this is advice to you; a strategy earns that once it beats the rest here.
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wider text-zinc-500">
            <tr>
              <th className="py-2 pr-3 font-medium">Strategy</th>
              <th className="py-2 pr-3 text-right font-medium">Return</th>
              <th className="py-2 pr-3 text-right font-medium">Won</th>
              <th className="py-2 pr-3 text-right font-medium">Up after 7d</th>
              <th className="py-2 pr-3 text-right font-medium">Up after 30d</th>
              <th className="py-2 text-right font-medium">Open</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {ranked.map((portfolio) => (
              <tr key={portfolio.strategy}>
                <td className="py-2 pr-3 font-medium">{portfolio.label}</td>
                <td className={`py-2 pr-3 text-right font-semibold tabular-nums ${pctTone(portfolio.avg_return_pct)}`}>
                  {formatPct(portfolio.avg_return_pct)}
                </td>
                <td className="py-2 pr-3 text-right tabular-nums">
                  {portfolio.closed > 0 ? `${formatRate(portfolio.win_rate)} of ${portfolio.closed}` : '—'}
                </td>
                <td className="py-2 pr-3 text-right tabular-nums">{hitRate(portfolio.scores?.['7'])}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{hitRate(portfolio.scores?.['30'])}</td>
                <td className="py-2 text-right tabular-nums">{portfolio.open}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 divide-y divide-zinc-100 dark:divide-zinc-800">
        {ranked.map((portfolio) => (
          <details key={portfolio.strategy} className="py-2">
            <summary className="cursor-pointer text-sm font-medium">
              {portfolio.label}{' '}
              <span className="text-xs font-normal text-zinc-500">
                {portfolio.positions.length} trade{portfolio.positions.length === 1 ? '' : 's'}
              </span>
            </summary>
            <PaperPositions portfolio={portfolio} onTickerClick={onTickerClick} />
          </details>
        ))}
      </div>
    </section>
  )
}

function splitList(value: string): string[] {
  return value
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

function formatHandles(handles: string[]): string {
  return handles.map((h) => `@${h}`).join(', ')
}

const FEED_MARKETS: { key: AdvisorFeedMarket; label: string }[] = [
  { key: 'stocks', label: 'Stocks' },
  { key: 'options', label: 'Options' },
  { key: 'crypto', label: 'Crypto' },
  { key: 'forex', label: 'Forex' },
]

function StrategyForm({
  strategy,
  onSave,
}: {
  strategy: AdvisorStrategy
  onSave: (draft: AdvisorStrategyDraft) => Promise<unknown>
}) {
  const {
    rules,
    watchlist,
    followed_traders: followed,
    feed_markets: markets,
    available_cash: cash, cash_currency: currency, updated_at: updatedAt } = strategy
  const [draftRules, setDraftRules] = useState(rules)
  const [draftWatchlist, setDraftWatchlist] = useState(watchlist.join(', '))
  const [draftFollowed, setDraftFollowed] = useState(formatHandles(followed))
  const [draftMarkets, setDraftMarkets] = useState(markets)
  const [draftCash, setDraftCash] = useState(cash == null ? '' : String(cash))
  const [draftCurrency, setDraftCurrency] = useState(currency ?? 'USD')
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')

  useEffect(() => setDraftRules(rules), [rules])
  useEffect(() => setDraftWatchlist(watchlist.join(', ')), [watchlist])
  useEffect(() => setDraftFollowed(formatHandles(followed)), [followed])
  useEffect(() => setDraftMarkets(markets), [markets])
  useEffect(() => setDraftCash(cash == null ? '' : String(cash)), [cash])
  useEffect(() => setDraftCurrency(currency ?? 'USD'), [currency])

  const currencies = CURRENCIES.includes(draftCurrency) ? CURRENCIES : [draftCurrency, ...CURRENCIES]

  const onSubmit = async (ev: FormEvent<HTMLFormElement>) => {
    ev.preventDefault()
    setStatus('saving')
    try {
      const symbols = splitList(draftWatchlist)
      const parsedCash = draftCash.trim() === '' ? null : Number(draftCash)
      if (parsedCash !== null && (!Number.isFinite(parsedCash) || parsedCash < 0)) {
        setStatus('error')
        return
      }
      await onSave({
        rules: draftRules,
        watchlist: symbols,
        followed_traders: splitList(draftFollowed).map((h) => h.replace(/^@/, '')),
        feed_markets: FEED_MARKETS.map((m) => m.key).filter((key) => draftMarkets.includes(key)),
        available_cash: parsedCash,
        cash_currency: draftCurrency,
      })
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
            className={inputClass}
          />
        </label>
        <div className="grid gap-1 text-xs font-medium text-zinc-500">
          <label htmlFor="advisor-followed">Traders you follow</label>
          <input
            id="advisor-followed"
            value={draftFollowed}
            onChange={(ev) => setDraftFollowed(ev.target.value)}
            placeholder="@ShardiB2, @someone"
            className={inputClass}
          />
          <span className="font-normal">
            When one of them posts about a ticker, Claude checks its fundamentals and technicals and suggests it only
            if both look good.
          </span>
        </div>
        <fieldset className="grid gap-1 text-xs font-medium text-zinc-500">
          <legend>Posts Claude reads</legend>
          <div className="flex flex-wrap gap-3 font-normal text-zinc-700 dark:text-zinc-300">
            {FEED_MARKETS.map(({ key, label }) => (
              <label key={key} className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={draftMarkets.includes(key)}
                  onChange={(ev) =>
                    setDraftMarkets((prev) =>
                      ev.target.checked ? [...prev, key] : prev.filter((m) => m !== key),
                    )
                  }
                />
                {label}
              </label>
            ))}
          </div>
          <span className="font-normal">
            Each check only turns posts from these feeds into ideas, the same split as the dashboard&apos;s pages.
          </span>
        </fieldset>
        <div className="grid gap-1 text-xs font-medium text-zinc-500">
          <label htmlFor="advisor-cash">Cash available to invest</label>
          <div className="flex gap-2">
            <input
              id="advisor-cash"
              type="number"
              min={0}
              step="any"
              inputMode="decimal"
              value={draftCash}
              onChange={(ev) => setDraftCash(ev.target.value)}
              placeholder="Not set"
              className={`${inputClass} w-40 tabular-nums`}
            />
            <select
              value={draftCurrency}
              onChange={(ev) => setDraftCurrency(ev.target.value)}
              aria-label="Cash currency"
              className={inputClass}
            >
              {currencies.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          </div>
          <span className="font-normal">Claude uses this to size buy ideas. Leave it empty to skip sizing.</span>
        </div>
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

function RecentChecks({ runs }: { runs: AdvisorRun[] }) {
  return (
    <section className={card}>
      <h2 className={heading}>Recent checks</h2>
      <p className="mt-1 text-xs text-zinc-500">
        Each scheduled check reads every post since the one before, from pre-market to after-hours.
      </p>
      {runs.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-500">No checks have run yet.</p>
      ) : (
        <ul className="mt-3 divide-y divide-zinc-100 dark:divide-zinc-800">
          {runs.map((run) => (
            <li key={run.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2 text-sm">
              <span className="w-32 shrink-0 text-xs text-zinc-500">{formatTime(run.ran_at)}</span>
              {run.session && (
                <span className="rounded-md bg-zinc-100 px-1.5 py-0.5 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                  {run.session}
                </span>
              )}
              {run.posts_read != null && (
                <span className="text-xs tabular-nums text-zinc-500">{run.posts_read} posts</span>
              )}
              <span className="min-w-0 flex-1 basis-64">{run.summary || '—'}</span>
            </li>
          ))}
        </ul>
      )}
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
  const { strategy, calls, runs, scorecard, paper, loading, error, saveStrategy } = useAdvisor()

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
      <PaperStrategies portfolios={paper} onTickerClick={onTickerClick} />
      <RecentChecks runs={runs} />
      <Journal calls={calls} onTickerClick={onTickerClick} />
      <StrategyForm strategy={strategy} onSave={saveStrategy} />
    </>
  )
}
