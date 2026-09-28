import { useMemo, useState } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { usePortfolioHistory } from '../hooks/usePortfolioHistory'
import { useCurrency } from '../contexts/CurrencyContext'
import CurrencySelector from './CurrencySelector'
import type { PortfolioHistoryPoint, PortfolioHistoryRange } from '../types'

const UP = '#10b981' // emerald-500
const DOWN = '#f43f5e' // rose-500

function percent(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function formatStamp(stamp: string, range: PortfolioHistoryRange): string {
  const parsed = new Date(stamp.length === 10 ? `${stamp}T00:00:00Z` : stamp)
  if (Number.isNaN(parsed.getTime())) return stamp

  if (range === '1W') {
    return parsed.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      timeZone: 'UTC',
    })
  }
  if (range === '5Y' || range === 'MAX') {
    return parsed.toLocaleDateString(undefined, {
      month: 'short',
      year: 'numeric',
      timeZone: 'UTC',
    })
  }
  return parsed.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

const SOURCE_LABEL: Record<PortfolioHistoryPoint['source'], string> = {
  snapshot: 'recorded snapshot',
  reconstructed: 'reconstructed from prices',
  live: 'live quote',
}

function ChartTooltip({
  active,
  payload,
  range,
}: {
  active?: boolean
  payload?: Array<{ payload: PortfolioHistoryPoint }>
  range: PortfolioHistoryRange
}) {
  const { format: moneyExact } = useCurrency()
  if (!active || !payload?.length) return null
  const point = payload[0].payload

  return (
    <div className="rounded-lg border border-zinc-200 bg-white/95 px-3 py-2 text-xs shadow-lg dark:border-zinc-700 dark:bg-zinc-900/95">
      <div className="font-semibold text-zinc-700 dark:text-zinc-200">
        {formatStamp(point.t, range)}
      </div>
      <div className="mt-1 font-mono text-sm text-zinc-900 dark:text-zinc-100">
        {moneyExact(point.value)}
      </div>
      <div
        className={
          point.pnl >= 0
            ? 'font-mono text-emerald-600 dark:text-emerald-400'
            : 'font-mono text-rose-600 dark:text-rose-400'
        }
      >
        {moneyExact(point.pnl)} ({percent(point.pnl_percent)})
      </div>
      <div className="mt-1 text-[10px] uppercase tracking-wide text-zinc-400">
        {SOURCE_LABEL[point.source]}
      </div>
    </div>
  )
}

export default function PortfolioValueChart() {
  const { history, range, setRange, ranges, loading, refreshing, error } =
    usePortfolioHistory()
  const [showTable, setShowTable] = useState(false)
  const { format } = useCurrency()
  const money = (value: number | null | undefined) =>
    format(value, { minimumFractionDigits: 0, maximumFractionDigits: 0 })
  const moneyExact = (value: number | null | undefined) => format(value)

  const points = history?.points ?? []
  const isUp = (history?.change ?? 0) >= 0
  const stroke = isUp ? UP : DOWN

  // Pad the domain so the area does not sit flush against the axes.
  const domain = useMemo<[number, number]>(() => {
    if (points.length === 0) return [0, 1]
    const values = points.flatMap((p) => [p.value, p.cost_basis])
    const min = Math.min(...values)
    const max = Math.max(...values)
    const pad = (max - min || Math.abs(max) || 1) * 0.08
    return [min - pad, max + pad]
  }, [points])

  const tableRows = useMemo(() => {
    if (points.length <= 24) return points
    const step = Math.ceil(points.length / 24)
    const sampled = points.filter((_, index) => index % step === 0)
    const last = points[points.length - 1]
    return sampled[sampled.length - 1] === last ? sampled : [...sampled, last]
  }, [points])

  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">
            Portfolio Value
          </h2>
          <div className="mt-1 flex flex-wrap items-baseline gap-2">
            <span className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
              {money(history?.end_value)}
            </span>
            <span
              className={`text-sm font-semibold ${
                isUp
                  ? 'text-emerald-600 dark:text-emerald-400'
                  : 'text-rose-600 dark:text-rose-400'
              }`}
            >
              {moneyExact(history?.change)} ({percent(history?.change_percent)}){' '}
              <span className="font-normal text-zinc-500">over {range}</span>
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Chart range">
            {(history?.available_ranges ?? ranges).map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => setRange(key)}
                aria-pressed={key === range}
                className={`rounded-md px-2 py-1 text-[11px] font-semibold transition-colors ${
                  key === range
                    ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                    : 'border border-zinc-300 text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800'
                }`}
              >
                {key}
              </button>
            ))}
          </div>
          <CurrencySelector />
        </div>
      </div>

      {error && <p className="mb-2 text-sm text-rose-500">{error}</p>}

      {loading ? (
        <div className="h-64 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
      ) : points.length === 0 ? (
        <p className="py-10 text-center text-sm text-zinc-500">
          No holdings to chart yet. Add a position or connect IBKR to start tracking value
          over time.
        </p>
      ) : (
        <div className={refreshing ? 'opacity-60 transition-opacity' : 'transition-opacity'}>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="portfolio-value-fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={stroke} stopOpacity={0.28} />
                    <stop offset="100%" stopColor={stroke} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  stroke="currentColor"
                  className="text-zinc-200 dark:text-zinc-800"
                  vertical={false}
                />
                <XAxis
                  dataKey="t"
                  tickFormatter={(value: string) => formatStamp(value, range)}
                  tick={{ fontSize: 11 }}
                  stroke="currentColor"
                  className="text-zinc-400"
                  minTickGap={32}
                  tickLine={false}
                />
                <YAxis
                  domain={domain}
                  tickFormatter={(value: number) => money(value)}
                  tick={{ fontSize: 11 }}
                  stroke="currentColor"
                  className="text-zinc-400"
                  width={72}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  content={<ChartTooltip range={range} />}
                  cursor={{ stroke: 'currentColor', strokeWidth: 1, className: 'text-zinc-400' }}
                />
                {history?.cost_basis ? (
                  <ReferenceLine
                    y={history.cost_basis}
                    stroke="currentColor"
                    className="text-zinc-400"
                    strokeDasharray="4 4"
                    label={{
                      value: `Cost basis ${money(history.cost_basis)}`,
                      position: 'insideTopLeft',
                      fontSize: 10,
                      fill: 'currentColor',
                      className: 'text-zinc-500',
                    }}
                  />
                ) : null}
                <Area
                  type="monotone"
                  dataKey="value"
                  name="Portfolio value"
                  stroke={stroke}
                  strokeWidth={2}
                  fill="url(#portfolio-value-fill)"
                  activeDot={{ r: 4, strokeWidth: 2 }}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-3 grid gap-2 text-xs sm:grid-cols-4">
            <div>
              <div className="text-zinc-500">Start of {range}</div>
              <div className="font-mono text-zinc-800 dark:text-zinc-200">
                {moneyExact(history?.start_value)}
              </div>
            </div>
            <div>
              <div className="text-zinc-500">Now</div>
              <div className="font-mono text-zinc-800 dark:text-zinc-200">
                {moneyExact(history?.end_value)}
              </div>
            </div>
            <div>
              <div className="text-zinc-500">Cost basis</div>
              <div className="font-mono text-zinc-800 dark:text-zinc-200">
                {moneyExact(history?.cost_basis)}
              </div>
            </div>
            <div>
              <div className="text-zinc-500">Holdings</div>
              <div className="font-mono text-zinc-800 dark:text-zinc-200">
                {history?.holdings.length ?? 0} ({history?.source})
              </div>
            </div>
          </div>

          {history?.missing_symbols?.length ? (
            <p className="mt-2 text-[11px] text-amber-600 dark:text-amber-400">
              No price history for {history.missing_symbols.join(', ')} — excluded from the
              chart.
            </p>
          ) : null}

          <button
            type="button"
            onClick={() => setShowTable((open) => !open)}
            className="mt-3 text-[11px] font-semibold text-zinc-500 underline underline-offset-2 hover:text-zinc-700 dark:hover:text-zinc-300"
          >
            {showTable ? 'Hide table view' : 'Show table view'}
          </button>

          {showTable && (
            <div className="mt-2 max-h-56 overflow-auto">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-white text-zinc-500 dark:bg-zinc-950">
                  <tr>
                    <th className="py-1">Date</th>
                    <th className="py-1 text-right">Value</th>
                    <th className="py-1 text-right">PnL</th>
                    <th className="py-1 text-right">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {tableRows.map((point) => (
                    <tr
                      key={point.t}
                      className="border-t border-zinc-100 dark:border-zinc-900"
                    >
                      <td className="py-1">{formatStamp(point.t, range)}</td>
                      <td className="py-1 text-right font-mono tabular-nums">
                        {moneyExact(point.value)}
                      </td>
                      <td
                        className={`py-1 text-right font-mono tabular-nums ${
                          point.pnl >= 0
                            ? 'text-emerald-600 dark:text-emerald-400'
                            : 'text-rose-600 dark:text-rose-400'
                        }`}
                      >
                        {percent(point.pnl_percent)}
                      </td>
                      <td className="py-1 text-right text-zinc-400">
                        {SOURCE_LABEL[point.source]}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
