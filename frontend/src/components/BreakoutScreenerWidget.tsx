import { useState } from 'react'
import { useBreakouts } from '../hooks/useBreakouts'
import type { PortfolioTickerLookup } from '../hooks/usePortfolioTickers'
import type { Breakout, BreakoutCheck, BreakoutCriteria, BreakoutHistory } from '../types'
import { PortfolioTickerBadge } from './PortfolioTickerBadge'

const BADGE_BASE = 'rounded-full px-2 py-0.5 text-[11px] font-semibold'
const BADGE_UP = 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
const BADGE_WARN = 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
const BADGE_NEUTRAL = 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'

/** What a near miss still lacks, in the words a reader would use. */
const MISSING: Record<BreakoutCheck, string> = {
  stage_2: 'not in stage 2',
  fresh: 'breakout too old',
  from_base: 'no proper base',
  relative_strength: 'lags the market',
  rs_rising: 'RS not rising',
  volume: 'light volume',
  not_extended: 'too extended',
}

type Tab = 'breakouts' | 'watch' | 'record'

function signed(value: number | null | undefined, digits = 1): string {
  if (value == null) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`
}

function toneClass(value: number | null | undefined): string {
  if (value == null || value === 0) return 'text-zinc-500'
  return value > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
}

function fmtDate(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(`${value.slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

function price(value: number | null | undefined): string {
  if (value == null) return '—'
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function ScoreBar({ score }: { score: number | null }) {
  const value = Math.max(0, Math.min(100, score ?? 0))
  return (
    <div className="flex items-center gap-2" title="Blend of relative strength, volume, freshness and distance from the 30-week average">
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
        <span className="block h-full rounded-full bg-emerald-500" style={{ width: `${value}%` }} />
      </div>
      <span className="tabular-nums text-xs text-zinc-600 dark:text-zinc-300">{score?.toFixed(0) ?? '—'}</span>
    </div>
  )
}

function SymbolCell({
  row,
  portfolioLookup,
  onTickerClick,
}: {
  row: Breakout
  portfolioLookup?: PortfolioTickerLookup
  onTickerClick?: (ticker: string) => void
}) {
  return (
    <td className="py-2 pr-3">
      <span className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onTickerClick?.(row.symbol)}
          className="font-mono text-sm font-semibold text-zinc-900 hover:underline dark:text-zinc-100"
        >
          {row.symbol}
        </button>
        <PortfolioTickerBadge status={portfolioLookup?.(row.symbol) ?? null} />
      </span>
      <span className="block max-w-[12rem] truncate text-[11px] text-zinc-500" title={[row.name, row.industry].filter(Boolean).join(' · ')}>
        {row.industry || row.sector || row.name || ''}
      </span>
    </td>
  )
}

function ScreenTable({
  rows,
  near,
  portfolioLookup,
  onTickerClick,
}: {
  rows: Breakout[]
  near: boolean
  portfolioLookup?: PortfolioTickerLookup
  onTickerClick?: (ticker: string) => void
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead>
          <tr className="text-[11px] uppercase tracking-wide text-zinc-500">
            <th className="pb-2 pr-3 font-medium">Stock</th>
            <th className="pb-2 pr-3 font-medium">{near ? 'Missing' : 'Score'}</th>
            <th className="pb-2 pr-3 font-medium" title="Weeks since price cleared its 30-week average">Broke out</th>
            <th className="pb-2 pr-3 font-medium" title="Weeks the stock based before the breakout">Base</th>
            <th className="pb-2 pr-3 text-right font-medium" title="Mansfield relative strength vs SPY">RS</th>
            <th className="pb-2 pr-3 text-right font-medium" title="Breakout week volume vs the 10 weeks before it">Volume</th>
            <th className="pb-2 pr-3 text-right font-medium" title="Price vs the 30-week average">vs 30w</th>
            <th className="pb-2 text-right font-medium">Price</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {rows.map((row) => (
            <tr key={`${row.symbol}-${row.breakout_week}`}>
              <SymbolCell row={row} portfolioLookup={portfolioLookup} onTickerClick={onTickerClick} />
              <td className="py-2 pr-3">
                {near ? (
                  <span className="flex flex-wrap gap-1">
                    {row.failed.map((check) => (
                      <span key={check} className={`${BADGE_BASE} ${BADGE_WARN}`}>
                        {MISSING[check] ?? check}
                      </span>
                    ))}
                  </span>
                ) : (
                  <ScoreBar score={row.score} />
                )}
              </td>
              <td className="py-2 pr-3 text-xs text-zinc-600 dark:text-zinc-300">
                {fmtDate(row.breakout_week)}
                {row.weeks_since_breakout != null && (
                  <span className="ml-1 text-zinc-500">({row.weeks_since_breakout}w)</span>
                )}
              </td>
              <td className="py-2 pr-3 text-xs tabular-nums text-zinc-600 dark:text-zinc-300">
                {row.base_weeks != null ? `${row.base_weeks}w` : '—'}
              </td>
              <td className={`py-2 pr-3 text-right text-xs tabular-nums ${toneClass(row.mansfield_rs)}`}>
                {signed(row.mansfield_rs)}
                {row.rs_rising_4w && <span className="ml-0.5" title="Rising over 4 weeks">↑</span>}
              </td>
              <td className="py-2 pr-3 text-right text-xs tabular-nums">
                {row.volume_ratio != null ? (
                  <span className={row.strong_volume ? 'font-semibold text-emerald-600 dark:text-emerald-400' : 'text-zinc-600 dark:text-zinc-300'}>
                    {row.volume_ratio.toFixed(1)}×
                  </span>
                ) : (
                  '—'
                )}
              </td>
              <td className="py-2 pr-3 text-right text-xs tabular-nums text-zinc-600 dark:text-zinc-300">
                {signed(row.price_vs_ma30w_percent)}
              </td>
              <td className="py-2 text-right text-xs tabular-nums text-zinc-700 dark:text-zinc-200">{price(row.close)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TrackRecord({
  history,
  portfolioLookup,
  onTickerClick,
}: {
  history: BreakoutHistory
  portfolioLookup?: PortfolioTickerLookup
  onTickerClick?: (ticker: string) => void
}) {
  const { summary, signals } = history
  if (signals.length === 0) {
    return (
      <p className="text-sm text-zinc-500">
        No breakouts flagged in the last {history.days} days yet. Each one the screen flags is kept here with its price that day,
        so this becomes the screen's own track record.
      </p>
    )
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-4 text-xs text-zinc-600 dark:text-zinc-300">
        <span>
          <span className="font-semibold text-zinc-900 dark:text-zinc-100">{summary.flagged}</span> flagged in {history.days} days
        </span>
        <span>
          Average since flagged{' '}
          <span className={`font-semibold ${toneClass(summary.avg_return_pct)}`}>{signed(summary.avg_return_pct)}</span>
        </span>
        <span>
          Up since flagged{' '}
          <span className="font-semibold text-zinc-900 dark:text-zinc-100">
            {summary.win_rate_pct != null ? `${summary.win_rate_pct.toFixed(0)}%` : '—'}
          </span>
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[480px] text-left text-sm">
          <thead>
            <tr className="text-[11px] uppercase tracking-wide text-zinc-500">
              <th className="pb-2 pr-3 font-medium">Stock</th>
              <th className="pb-2 pr-3 font-medium">Flagged</th>
              <th className="pb-2 pr-3 text-right font-medium">Then</th>
              <th className="pb-2 pr-3 text-right font-medium">Now</th>
              <th className="pb-2 text-right font-medium">Return</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {signals.map((row) => (
              <tr key={`${row.symbol}-${row.breakout_week}`}>
                <SymbolCell row={row} portfolioLookup={portfolioLookup} onTickerClick={onTickerClick} />
                <td className="py-2 pr-3 text-xs text-zinc-600 dark:text-zinc-300">{fmtDate(row.flagged_at)}</td>
                <td className="py-2 pr-3 text-right text-xs tabular-nums text-zinc-600 dark:text-zinc-300">{price(row.flag_price)}</td>
                <td className="py-2 pr-3 text-right text-xs tabular-nums text-zinc-600 dark:text-zinc-300">{price(row.last_close)}</td>
                <td className={`py-2 text-right text-xs font-semibold tabular-nums ${toneClass(row.return_since_flag_pct)}`}>
                  {signed(row.return_since_flag_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function criteriaLine(criteria: BreakoutCriteria | null): string {
  if (!criteria) return 'Weekly stage 2: above a rising 30-week average, out of a base, with relative strength and volume'
  return (
    `Cleared a rising ${criteria.ma_weeks}-week average in the last ${criteria.fresh_weeks} weeks after a ` +
    `${criteria.min_base_weeks}+ week base, beating SPY, on ${criteria.min_volume_ratio}× volume, ` +
    `at most ${criteria.max_extension_pct}% above the average`
  )
}

interface Props {
  portfolioLookup?: PortfolioTickerLookup
  onTickerClick?: (ticker: string) => void
}

export default function BreakoutScreenerWidget({ portfolioLookup, onTickerClick }: Props) {
  const { screen, history, loading, error } = useBreakouts()
  const [tab, setTab] = useState<Tab>('breakouts')

  const run = screen?.run ?? null
  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: 'breakouts', label: 'Breakouts', count: screen?.breakouts.length },
    { key: 'watch', label: 'Near misses', count: screen?.watch.length },
    { key: 'record', label: 'Track record', count: history.summary.flagged || undefined },
  ]

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Stage 2 Breakouts</h2>
          <p className="text-[11px] text-zinc-500">{criteriaLine(screen?.criteria ?? null)}</p>
        </div>
        <span className={`${BADGE_BASE} ${run && screen && screen.breakouts.length > 0 ? BADGE_UP : BADGE_NEUTRAL}`}>
          {run ? `Week of ${fmtDate(run.as_of)} · ${run.evaluated} screened` : 'WEEKLY'}
        </span>
      </div>

      <div className="mb-3 flex flex-wrap gap-1" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              tab === t.key
                ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
            }`}
          >
            {t.label}
            {t.count != null && <span className="ml-1 opacity-70">{t.count}</span>}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-8 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-rose-600 dark:text-rose-400">Couldn't load the breakout screen.</p>
      ) : tab === 'record' ? (
        <TrackRecord history={history} portfolioLookup={portfolioLookup} onTickerClick={onTickerClick} />
      ) : !run ? (
        <p className="text-sm text-zinc-500">
          The first screen is still running. It reads a few hundred stocks' weekly charts, so give it a few minutes after the backend starts.
        </p>
      ) : (tab === 'breakouts' ? screen!.breakouts : screen!.watch).length === 0 ? (
        <p className="text-sm text-zinc-500">
          {tab === 'breakouts'
            ? 'No stock passes every check this week. Breakouts cluster when the market turns up out of a correction.'
            : 'No fresh stage-2 entry is one check away right now.'}
        </p>
      ) : (
        <ScreenTable
          rows={tab === 'breakouts' ? screen!.breakouts : screen!.watch}
          near={tab === 'watch'}
          portfolioLookup={portfolioLookup}
          onTickerClick={onTickerClick}
        />
      )}
    </div>
  )
}
