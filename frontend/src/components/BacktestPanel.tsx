import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useBacktest } from '../hooks/useBacktest'
import type { BacktestAccount, BacktestAccountWindow, BacktestReport, BacktestVariant } from '../types'

const card =
  'rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900'
const heading = 'text-sm font-semibold uppercase tracking-wider text-zinc-500'
const subheading = 'text-xs font-semibold uppercase tracking-wider text-zinc-500'
const th = 'py-2 pr-3 font-medium'
const thRight = 'py-2 pr-3 text-right font-medium'
const td = 'py-1.5 pr-3 text-right tabular-nums'

const GROUP_LABELS: Record<BacktestVariant['group'], string> = {
  baseline: 'Now',
  accounts: 'Who to follow',
  entry: 'Entry filter',
  exit: 'Exit rules',
  sizing: 'Sizing',
}

const CURRENT = '#71717a'
const COMPARE = '#2563eb'

function pct(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`
}

function rate(value: number | null | undefined): string {
  return value == null ? '—' : `${Math.round(value * 100)}%`
}

function tone(value: number | null | undefined): string {
  if (value == null || value === 0) return ''
  return value > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'
}

function reasonLabel(reason: string): string {
  return reason.replace(/_/g, ' ')
}

function EquityChart({ current, compare }: { current: BacktestVariant; compare: BacktestVariant | null }) {
  const data = useMemo(() => {
    const other = new Map((compare?.curve ?? []).map((p) => [p.t, p.equity]))
    const base = current.curve[0]?.equity || 1
    const otherBase = compare?.curve[0]?.equity || 1
    return current.curve.map((p) => ({
      t: p.t,
      current: +((p.equity / base - 1) * 100).toFixed(2),
      compare: other.has(p.t) ? +(((other.get(p.t) as number) / otherBase - 1) * 100).toFixed(2) : undefined,
    }))
  }, [current, compare])

  return (
    <div className="h-48 w-full text-zinc-500" aria-label="Equity curve">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="currentColor" strokeOpacity={0.12} vertical={false} />
          <XAxis dataKey="t" stroke="currentColor" fontSize={11} tickLine={false} minTickGap={40} />
          <YAxis
            stroke="currentColor"
            fontSize={11}
            tickLine={false}
            width={44}
            tickFormatter={(v: number) => `${v}%`}
          />
          <Tooltip
            formatter={(value, name) => [
              pct(Number(value)),
              name === 'current' ? current.label : (compare?.label ?? ''),
            ]}
            contentStyle={{ fontSize: 12 }}
          />
          <Line type="monotone" dataKey="current" stroke={CURRENT} strokeWidth={2} dot={false} />
          {compare && compare.key !== current.key && (
            <Line type="monotone" dataKey="compare" stroke={COMPARE} strokeWidth={2} dot={false} />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function VariantTable({
  report,
  selected,
  onSelect,
}: {
  report: BacktestReport
  selected: string
  onSelect: (key: string) => void
}) {
  const spy = report.benchmark?.return_pct ?? null
  let lastGroup = ''
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[620px] text-left text-sm">
        <thead className="text-xs uppercase tracking-wider text-zinc-500">
          <tr>
            <th className={th}>Variant</th>
            <th className={thRight}>Return</th>
            <th className={thRight}>vs SPY</th>
            <th className={thRight}>Max drawdown</th>
            <th className={thRight}>Trades</th>
            <th className={thRight}>Won</th>
            <th className="py-2 text-right font-medium">Still open</th>
          </tr>
        </thead>
        <tbody>
          {report.variants.map((v) => {
            const header = v.group !== lastGroup
            lastGroup = v.group
            const isSelected = v.key === selected
            return (
              <FragmentRows key={v.key} header={header ? GROUP_LABELS[v.group] : null}>
                <tr
                  onClick={() => onSelect(v.key)}
                  className={`cursor-pointer border-t border-zinc-100 dark:border-zinc-800 ${
                    isSelected ? 'bg-blue-50 dark:bg-blue-500/10' : 'hover:bg-zinc-50 dark:hover:bg-zinc-800/50'
                  }`}
                  aria-selected={isSelected}
                >
                  <td className={`py-1.5 pr-3 ${v.group === 'baseline' ? 'font-semibold' : ''}`}>{v.label}</td>
                  <td className={`${td} font-semibold ${tone(v.return_pct)}`}>{pct(v.return_pct)}</td>
                  <td className={`${td} ${tone(spy == null ? null : v.return_pct - spy)}`}>
                    {spy == null ? '—' : pct(v.return_pct - spy)}
                  </td>
                  <td className={`${td} text-red-600 dark:text-red-400`}>{pct(v.max_drawdown_pct)}</td>
                  <td className={td}>{v.trades}</td>
                  <td className={td}>{rate(v.win_rate)}</td>
                  <td className="py-1.5 text-right tabular-nums">{v.open_positions}</td>
                </tr>
              </FragmentRows>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function FragmentRows({ header, children }: { header: string | null; children: React.ReactNode }) {
  return (
    <>
      {header && (
        <tr>
          <td colSpan={7} className={`${subheading} pb-1 pt-3`}>
            {header}
          </td>
        </tr>
      )}
      {children}
    </>
  )
}

function TradeLog({ variant }: { variant: BacktestVariant }) {
  if (!variant.trade_log?.length) return null
  return (
    <details className="mt-3">
      <summary className="cursor-pointer text-sm font-medium">
        Trades under the current rules{' '}
        <span className="text-xs font-normal text-zinc-500">{variant.trade_log.length}</span>
      </summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wider text-zinc-500">
            <tr>
              <th className={th}>Symbol</th>
              <th className={th}>Bought</th>
              <th className={th}>Called by</th>
              <th className={th}>Exit</th>
              <th className="py-2 text-right font-medium">Return</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {variant.trade_log.map((t) => (
              <tr key={`${t.symbol}-${t.entry_day}`}>
                <td className="py-1.5 pr-3 font-medium">{t.symbol}</td>
                <td className="py-1.5 pr-3 tabular-nums text-zinc-500">{t.entry_day}</td>
                <td className="py-1.5 pr-3 text-zinc-500">{t.accounts.map((a) => `@${a}`).join(', ')}</td>
                <td className="py-1.5 pr-3 text-zinc-500">
                  {t.exit_reason === 'open'
                    ? 'still open'
                    : `${t.rules_hit.map(reasonLabel).join(', ')} on ${t.exit_day}`}
                </td>
                <td className={`py-1.5 text-right tabular-nums ${tone(t.return_pct)}`}>{pct(t.return_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}

function ExitStudy({ report }: { report: BacktestReport }) {
  const study = report.exit_study
  if (!study || study.rows.length === 0) return null
  return (
    <div className="mt-5">
      <h3 className={subheading}>Exit rules over 3 years</h3>
      <p className="mt-1 text-xs text-zinc-500">
        A buy every month in each of the {study.symbols} stocks the accounts mention, whenever it closed above its
        200-day ({study.entries.toLocaleString()} entries, {study.first_entry} to {study.last_entry}), sold by each
        rule. Return per year held puts long and short holds on one footing.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[620px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wider text-zinc-500">
            <tr>
              <th className={th}>Exit</th>
              <th className={thRight}>Avg return</th>
              <th className={thRight}>Median</th>
              <th className={thRight}>Won</th>
              <th className={thRight}>Days held</th>
              <th className={thRight}>Per year held</th>
              <th className="py-2 text-right font-medium">Worst 10%</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {study.rows.map((row) => (
              <tr key={row.key}>
                <td className={`py-1.5 pr-3 ${row.key === 'current' ? 'font-semibold' : ''}`}>{row.label}</td>
                <td className={`${td} ${tone(row.avg_return_pct)}`}>{pct(row.avg_return_pct)}</td>
                <td className={`${td} ${tone(row.median_return_pct)}`}>{pct(row.median_return_pct)}</td>
                <td className={td}>{rate(row.win_rate)}</td>
                <td className={td}>{Math.round(row.avg_days_held)}</td>
                <td className={`${td} font-semibold ${tone(row.return_per_year_held_pct)}`}>
                  {pct(row.return_per_year_held_pct)}
                </td>
                <td className={`py-1.5 text-right tabular-nums ${tone(row.p10_pct)}`}>{pct(row.p10_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function WindowCells({ w }: { w: BacktestAccountWindow | null }) {
  if (!w) {
    return (
      <>
        <td className={`${td} text-zinc-400`}>—</td>
        <td className={`${td} text-zinc-400`}>—</td>
        <td className={`${td} text-zinc-400`}>—</td>
      </>
    )
  }
  return (
    <>
      <td className={td}>{w.signals}</td>
      <td className={td}>{rate(w.hit_rate)}</td>
      <td className={`${td} ${tone(w.avg_excess_pct)}`}>{pct(w.avg_excess_pct)}</td>
    </>
  )
}

const ACCOUNT_ROWS = 15

function Accounts({ accounts }: { accounts: BacktestAccount[] }) {
  const [all, setAll] = useState(false)
  if (accounts.length === 0) return null
  const shown = all
    ? accounts
    : accounts.filter((a, i) => i < ACCOUNT_ROWS || a.followed)
  return (
    <div className="mt-5">
      <h3 className={subheading}>Accounts</h3>
      <p className="mt-1 text-xs text-zinc-500">
        Each account's bullish calls, bought at the next close: share that were up, and the average return beyond
        SPY's over the same days. Followed accounts are marked.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[620px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wider text-zinc-500">
            <tr>
              <th className={th} rowSpan={2}>
                Account
              </th>
              <th className="pr-3 pt-2 text-right font-medium" colSpan={3}>
                After 5 days
              </th>
              <th className="pt-2 text-right font-medium" colSpan={3}>
                After 20 days
              </th>
            </tr>
            <tr>
              <th className={thRight}>Calls</th>
              <th className={thRight}>Up</th>
              <th className={thRight}>vs SPY</th>
              <th className={thRight}>Calls</th>
              <th className={thRight}>Up</th>
              <th className={thRight}>vs SPY</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {shown.map((a) => (
              <tr key={a.account}>
                <td className="py-1.5 pr-3">
                  @{a.account}
                  {a.followed && (
                    <span className="ml-2 rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-blue-700 dark:bg-blue-500/15 dark:text-blue-300">
                      followed
                    </span>
                  )}
                </td>
                <WindowCells w={a.d5} />
                <WindowCells w={a.d20} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {accounts.length > shown.length && (
        <button type="button" className="mt-2 text-xs font-medium text-blue-600 dark:text-blue-400" onClick={() => setAll(true)}>
          Show all {accounts.length} accounts
        </button>
      )}
    </div>
  )
}

export default function BacktestPanel() {
  const { data, failed, rerun } = useBacktest()
  const [selected, setSelected] = useState<string | null>(null)
  const report = data?.result ?? null
  const running = data?.status === 'running'

  const current = report?.variants.find((v) => v.key === 'current') ?? report?.variants[0] ?? null
  const best = useMemo(() => {
    if (!report?.variants.length) return null
    return [...report.variants].sort((a, b) => b.return_pct - a.return_pct)[0]
  }, [report])
  const compareKey = selected ?? best?.key ?? null
  const compare = report?.variants.find((v) => v.key === compareKey) ?? null

  return (
    <section className={card} aria-label="Backtest">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className={heading}>Backtest</h2>
          <p className="mt-1 text-xs text-zinc-500">
            Your rules replayed on every stored call and daily prices, one change at a time, starting with $10,000.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void rerun()}
          disabled={running}
          className="rounded-lg border border-zinc-300 px-2.5 py-1 text-xs font-medium text-zinc-700 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-200"
        >
          {running ? 'Running…' : 'Run again'}
        </button>
      </div>

      {failed && !report && <p className="mt-3 text-sm text-red-500">Failed to load the backtest.</p>}
      {data?.status === 'error' && <p className="mt-3 text-sm text-red-500">The last run failed: {data.error}</p>}
      {!report && running && (
        <p className="mt-3 text-sm text-zinc-500">
          Running: reading a few hundred price histories takes a minute or two.
        </p>
      )}
      {report && !report.window && (
        <p className="mt-3 text-sm text-zinc-500">No stored stock calls with prices to replay yet.</p>
      )}

      {report?.window && current && (
        <>
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-300">
            {report.signals.toLocaleString()} bullish calls from {report.accounts_seen} accounts on{' '}
            {report.symbols_priced} stocks, {report.window.start} to {report.window.end}. SPY did{' '}
            <span className={tone(report.benchmark?.return_pct)}>{pct(report.benchmark?.return_pct)}</span> over the
            same days.
          </p>
          <div className="mt-3">
            <EquityChart current={current} compare={compare} />
            <p className="mt-1 text-xs text-zinc-500">
              <span className="font-semibold" style={{ color: CURRENT }}>
                ━
              </span>{' '}
              {current.label}
              {compare && compare.key !== current.key && (
                <>
                  {'  '}
                  <span className="ml-3 font-semibold" style={{ color: COMPARE }}>
                    ━
                  </span>{' '}
                  {compare.label} {selected ? '' : '(best)'}
                </>
              )}
              . Click a row to compare.
            </p>
          </div>
          <div className="mt-3">
            <VariantTable report={report} selected={compareKey ?? ''} onSelect={setSelected} />
          </div>
          <TradeLog variant={current} />
          <ExitStudy report={report} />
          <Accounts accounts={report.accounts} />
          <details className="mt-4 text-xs text-zinc-500">
            <summary className="cursor-pointer font-medium">What the replay assumes</summary>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {report.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </details>
          {report.computed_at && (
            <p className="mt-2 text-xs text-zinc-400">
              Computed {new Date(report.computed_at).toLocaleString()}
              {running ? '; a new run is going.' : ''}
            </p>
          )}
        </>
      )}
    </section>
  )
}
