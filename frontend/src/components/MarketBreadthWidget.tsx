import { useState } from 'react'
import { Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useMarketBreadth, useMarketBreadthHistory } from '../hooks/useMarketBreadth'
import type { BreadthDay, BreadthTrend, BreadthUniverse, MarketBreadth } from '../types'

const BADGE_BASE = 'rounded-full px-2 py-0.5 text-[11px] font-semibold'
const BADGE_UP = 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
const BADGE_DOWN = 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
const BADGE_WARN = 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
const BADGE_NEUTRAL = 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'

const TREND_BADGE: Record<BreadthTrend, string> = {
  overbought: BADGE_WARN,
  healthy: BADGE_UP,
  mixed: BADGE_NEUTRAL,
  weak: BADGE_DOWN,
  washed_out: BADGE_WARN,
}

const DAY_LABEL: Record<BreadthDay, { label: string; className: string }> = {
  broad_rally: { label: 'Broad rally', className: BADGE_UP },
  narrow_rally: { label: 'Narrow rally', className: BADGE_WARN },
  broad_selloff: { label: 'Broad sell-off', className: BADGE_DOWN },
  resilient: { label: 'Members holding up', className: BADGE_UP },
  mixed: { label: 'Mixed day', className: BADGE_NEUTRAL },
}

const SMA_ROWS: Array<{ field: 'pct_above_sma20' | 'pct_above_sma50' | 'pct_above_sma200'; label: string }> = [
  { field: 'pct_above_sma20', label: '20-day' },
  { field: 'pct_above_sma50', label: '50-day' },
  { field: 'pct_above_sma200', label: '200-day' },
]

const LINE_50 = '#0ea5e9'
const LINE_200 = '#a855f7'

function signed(value: number | null, digits = 2): string {
  if (value == null) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`
}

function toneClass(value: number | null): string {
  if (value == null || value === 0) return 'text-zinc-500'
  return value > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
}

function pct(value: number | null): string {
  return value == null ? '—' : `${value.toFixed(0)}%`
}

function barTone(value: number | null): string {
  if (value == null) return 'bg-zinc-300 dark:bg-zinc-700'
  if (value >= 60) return 'bg-emerald-500'
  if (value >= 40) return 'bg-amber-400'
  return 'bg-rose-500'
}

function AdvanceDeclineBar({ universe }: { universe: BreadthUniverse }) {
  const total = Math.max(universe.members, 1)
  return (
    <div>
      <div
        className="flex h-2 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800"
        aria-label={`${universe.advancers} advancing, ${universe.decliners} declining`}
      >
        <span className="bg-emerald-500" style={{ width: `${(universe.advancers / total) * 100}%` }} />
        <span className="bg-zinc-300 dark:bg-zinc-600" style={{ width: `${(universe.unchanged / total) * 100}%` }} />
        <span className="bg-rose-500" style={{ width: `${(universe.decliners / total) * 100}%` }} />
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-zinc-500">
        <span className="text-emerald-600 dark:text-emerald-400">{universe.advancers} up</span>
        <span className="text-rose-600 dark:text-rose-400">{universe.decliners} down</span>
      </div>
    </div>
  )
}

function UniverseCard({
  universe,
  selected,
  onSelect,
}: {
  universe: BreadthUniverse
  selected: boolean
  onSelect: () => void
}) {
  const trend = universe.read.trend
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`rounded-lg border p-3 text-left transition-colors ${
        selected
          ? 'border-sky-400 bg-sky-50 dark:border-sky-600 dark:bg-sky-950/30'
          : 'border-zinc-200 bg-zinc-50 hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-900/60 dark:hover:border-zinc-700'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">{universe.label}</span>
        {trend && <span className={`${BADGE_BASE} ${TREND_BADGE[trend.key]}`}>{trend.label}</span>}
      </div>
      <div className="mt-2 flex items-end justify-between gap-2">
        <div>
          <p className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{pct(universe.pct_above_sma200)}</p>
          <p className="text-[11px] text-zinc-500">above 200-day average</p>
        </div>
        <div className="text-right">
          <p className={`text-sm font-semibold ${toneClass(universe.benchmark.change_pct)}`}>
            {signed(universe.benchmark.change_pct)}
          </p>
          <p className="text-[11px] text-zinc-500">{universe.benchmark.symbol}</p>
        </div>
      </div>
      <div className="mt-2">
        <AdvanceDeclineBar universe={universe} />
      </div>
    </button>
  )
}

function shortDate(value: string): string {
  const [, month, day] = value.split('-')
  return `${Number(month)}/${Number(day)}`
}

function HistoryChart({ universe }: { universe: BreadthUniverse }) {
  const points = useMarketBreadthHistory(universe.key)
  if (points.length < 2) {
    return (
      <p className="py-6 text-center text-xs text-zinc-500">
        The trend chart fills in as each trading session is recorded.
      </p>
    )
  }
  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <XAxis
            dataKey="session_date"
            tickFormatter={shortDate}
            tick={{ fontSize: 11 }}
            stroke="currentColor"
            className="text-zinc-400"
            minTickGap={32}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            ticks={[0, 25, 50, 75, 100]}
            tickFormatter={(value: number) => `${value}%`}
            tick={{ fontSize: 11 }}
            stroke="currentColor"
            className="text-zinc-400"
            width={40}
            tickLine={false}
            axisLine={false}
          />
          <ReferenceLine y={50} stroke="currentColor" className="text-zinc-300 dark:text-zinc-700" strokeDasharray="4 4" />
          <Tooltip
            formatter={(value, name) => [`${Number(value).toFixed(1)}%`, String(name)]}
            labelFormatter={(label) => String(label)}
            contentStyle={{ fontSize: 12 }}
          />
          <Line
            type="monotone"
            dataKey="pct_above_sma50"
            name="Above 50-day"
            stroke={LINE_50}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="pct_above_sma200"
            name="Above 200-day"
            stroke={LINE_200}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function UniverseDetail({ universe }: { universe: BreadthUniverse }) {
  const day = DAY_LABEL[universe.read.day]
  return (
    <section className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900/60">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{universe.label} participation</h3>
        <span className={`${BADGE_BASE} ${day.className}`}>{day.label}</span>
      </div>
      <p className="text-sm text-zinc-700 dark:text-zinc-300">{universe.read.note}</p>
      <div className="mt-3 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <div className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Members above their</p>
          {SMA_ROWS.map(({ field, label }) => (
            <div key={field}>
              <div className="flex justify-between text-xs">
                <span className="text-zinc-600 dark:text-zinc-400">{label} average</span>
                <span className="font-semibold text-zinc-800 dark:text-zinc-200">{pct(universe[field])}</span>
              </div>
              <div className="mt-0.5 h-1.5 rounded-full bg-zinc-200 dark:bg-zinc-800">
                <div
                  className={`h-1.5 rounded-full ${barTone(universe[field])}`}
                  style={{ width: `${Math.min(100, Math.max(0, universe[field] ?? 0))}%` }}
                />
              </div>
            </div>
          ))}
          <div className="grid grid-cols-2 gap-2 pt-1">
            <div className="rounded-md bg-white p-2 text-center dark:bg-zinc-900">
              <p className="text-lg font-semibold text-emerald-600 dark:text-emerald-400">{universe.new_highs}</p>
              <p className="text-[11px] text-zinc-500">52-week highs</p>
            </div>
            <div className="rounded-md bg-white p-2 text-center dark:bg-zinc-900">
              <p className="text-lg font-semibold text-rose-600 dark:text-rose-400">{universe.new_lows}</p>
              <p className="text-[11px] text-zinc-500">52-week lows</p>
            </div>
          </div>
        </div>
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-3 text-[11px] text-zinc-500">
            <span className="flex items-center gap-1">
              <span className="h-0.5 w-3" style={{ background: LINE_50 }} /> Above 50-day
            </span>
            <span className="flex items-center gap-1">
              <span className="h-0.5 w-3" style={{ background: LINE_200 }} /> Above 200-day
            </span>
          </div>
          <HistoryChart universe={universe} />
        </div>
      </div>
    </section>
  )
}

function SectorTable({ sectors }: { sectors: MarketBreadth['sectors'] }) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900/60">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">S&amp;P 500 sectors</h3>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-xs">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-zinc-500">
              <th className="py-1 pr-2 font-medium">Sector</th>
              <th className="py-1 pr-2 font-medium">Above 50-day</th>
              <th className="py-1 pr-2 text-right font-medium">Above 200-day</th>
              <th className="py-1 pr-2 text-right font-medium">Up / down</th>
              <th className="py-1 pr-2 text-right font-medium">Highs / lows</th>
              <th className="py-1 text-right font-medium">Avg move</th>
            </tr>
          </thead>
          <tbody>
            {sectors.map((sector) => (
              <tr key={sector.sector} className="border-t border-zinc-200 dark:border-zinc-800">
                <td className="py-1.5 pr-2 text-zinc-800 dark:text-zinc-200">
                  {sector.sector} <span className="text-zinc-400">({sector.members})</span>
                </td>
                <td className="py-1.5 pr-2">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-20 rounded-full bg-zinc-200 dark:bg-zinc-800">
                      <div
                        className={`h-1.5 rounded-full ${barTone(sector.pct_above_sma50)}`}
                        style={{ width: `${sector.pct_above_sma50 ?? 0}%` }}
                      />
                    </div>
                    <span className="text-zinc-700 dark:text-zinc-300">{pct(sector.pct_above_sma50)}</span>
                  </div>
                </td>
                <td className="py-1.5 pr-2 text-right text-zinc-700 dark:text-zinc-300">{pct(sector.pct_above_sma200)}</td>
                <td className="py-1.5 pr-2 text-right">
                  <span className="text-emerald-600 dark:text-emerald-400">{sector.advancers}</span>
                  <span className="text-zinc-400"> / </span>
                  <span className="text-rose-600 dark:text-rose-400">{sector.decliners}</span>
                </td>
                <td className="py-1.5 pr-2 text-right text-zinc-600 dark:text-zinc-400">
                  {sector.new_highs} / {sector.new_lows}
                </td>
                <td className={`py-1.5 text-right font-medium ${toneClass(sector.avg_change)}`}>
                  {signed(sector.avg_change)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default function MarketBreadthWidget() {
  const { data, loading, error } = useMarketBreadth()
  const [selectedKey, setSelectedKey] = useState('spx')
  const selected = data?.universes.find((u) => u.key === selectedKey) ?? data?.universes[0]

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Market Breadth</h2>
        {data?.session_date && <span className="text-[11px] text-zinc-400">Session {data.session_date}</span>}
      </div>

      {loading ? (
        <div className="grid gap-3 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-32 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error || !data ? (
        <p className="text-sm text-red-500">Could not load market breadth.</p>
      ) : !selected ? (
        <p className="py-4 text-center text-xs text-zinc-500">No breadth data available right now.</p>
      ) : (
        <div className="space-y-3">
          <div className="grid gap-3 md:grid-cols-3">
            {data.universes.map((universe) => (
              <UniverseCard
                key={universe.key}
                universe={universe}
                selected={universe.key === selected.key}
                onSelect={() => setSelectedKey(universe.key)}
              />
            ))}
          </div>
          <UniverseDetail universe={selected} />
          {data.sectors.length > 0 && <SectorTable sectors={data.sectors} />}
          <p className="text-[11px] text-zinc-400">
            Computed from every index member on TradingView's scanner. A rally that most members sit out is
            fragile; more than ~80% above the 200-day average has historically meant stretched, under ~20%
            washed out. A new high or low means today's range touched the 52-week extreme.
          </p>
        </div>
      )}
    </div>
  )
}
