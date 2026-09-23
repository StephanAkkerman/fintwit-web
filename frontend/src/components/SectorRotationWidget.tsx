import { useMemo, useState } from 'react'
import {
  CartesianGrid,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useSectorRotation } from '../hooks/useSectorRotation'
import type { SectorRotationPoint, SectorRotationQuadrant, SectorRotationTimeframe } from '../types'
import { getSectorChartColor, getSectorStyle } from '../utils/sectorStyle'

const TIMEFRAME_OPTIONS: Array<{ key: SectorRotationTimeframe; label: string }> = [
  { key: 'daily', label: 'Daily' },
  { key: 'weekly', label: 'Weekly' },
]

const QUADRANT_ORDER: SectorRotationQuadrant[] = ['improving', 'leading', 'lagging', 'weakening']

const QUADRANT_META: Record<
  SectorRotationQuadrant,
  { label: string; wash: string; badge: string }
> = {
  leading: { label: 'Leading', wash: '#10b981', badge: 'text-emerald-600 dark:text-emerald-400' },
  weakening: { label: 'Weakening', wash: '#f59e0b', badge: 'text-amber-600 dark:text-amber-400' },
  lagging: { label: 'Lagging', wash: '#f43f5e', badge: 'text-rose-600 dark:text-rose-400' },
  improving: { label: 'Improving', wash: '#0ea5e9', badge: 'text-sky-600 dark:text-sky-400' },
}

type ChartPoint = SectorRotationPoint & {
  sector: string
  etf: string
  quadrant: SectorRotationQuadrant
  order: number
  total: number
  isLast: boolean
}

type DotProps = Partial<ChartPoint> & { cx?: number; cy?: number; color: string }

function SectorTrailDot(props: DotProps) {
  const { cx, cy, color, isLast, order = 0, total = 1, etf } = props
  if (cx == null || cy == null) return null

  const progress = total > 1 ? order / (total - 1) : 1
  const radius = isLast ? 6 : 3 + progress * 1.5
  const opacity = isLast ? 1 : 0.25 + progress * 0.5

  return (
    <g>
      {/* Generous transparent hit area so a thin trail dot is still easy to hover. */}
      <circle cx={cx} cy={cy} r={12} fill="transparent" />
      {isLast && (
        <circle cx={cx} cy={cy} r={radius + 2} fill="currentColor" className="text-white dark:text-zinc-900" />
      )}
      <circle cx={cx} cy={cy} r={radius} fill={color} fillOpacity={opacity} />
      {isLast && (
        <text
          x={cx + radius + 4}
          y={cy + 3}
          fontSize={10}
          fontWeight={600}
          fill="currentColor"
          className="text-zinc-600 dark:text-zinc-300"
        >
          {etf}
        </text>
      )}
    </g>
  )
}

function RRGTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: Array<{ payload: ChartPoint }>
}) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload
  const style = getSectorStyle(point.sector)
  const meta = QUADRANT_META[point.quadrant]

  return (
    <div className="rounded-lg border border-zinc-200 bg-white/95 px-3 py-2 text-xs shadow-lg dark:border-zinc-700 dark:bg-zinc-900/95">
      <div className="flex items-center gap-1.5 font-semibold text-zinc-700 dark:text-zinc-200">
        <span aria-hidden="true">{style.emoji}</span>
        {point.sector}
        <span className="font-normal text-zinc-400">({point.etf})</span>
      </div>
      <div className="mt-0.5 text-zinc-500">{point.date}</div>
      <div className="mt-1 grid grid-cols-2 gap-x-3 font-mono">
        <span className="text-zinc-500">RS-Ratio</span>
        <span className="text-right text-zinc-800 dark:text-zinc-100">{point.rs_ratio.toFixed(2)}</span>
        <span className="text-zinc-500">RS-Momentum</span>
        <span className="text-right text-zinc-800 dark:text-zinc-100">{point.rs_momentum.toFixed(2)}</span>
      </div>
      <div className={`mt-1 text-[10px] font-semibold uppercase tracking-wide ${meta.badge}`}>
        {meta.label}
      </div>
    </div>
  )
}

export default function SectorRotationWidget() {
  const [timeframe, setTimeframe] = useState<SectorRotationTimeframe>('daily')
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [showTable, setShowTable] = useState(false)
  const { data, loading, error } = useSectorRotation(timeframe)

  const toggleSector = (sector: string) => {
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(sector)) next.delete(sector)
      else next.add(sector)
      return next
    })
  }

  const visibleData = useMemo(() => data.filter((s) => !hidden.has(s.sector)), [data, hidden])

  const chartSeries = useMemo(
    () =>
      visibleData.map((s) => ({
        sector: s.sector,
        color: getSectorChartColor(s.sector),
        points: s.trail.map((p, i, arr) => ({
          ...p,
          sector: s.sector,
          etf: s.etf,
          quadrant: s.quadrant,
          order: i,
          total: arr.length,
          isLast: i === arr.length - 1,
        })) as ChartPoint[],
      })),
    [visibleData]
  )

  const domain = useMemo<[number, number]>(() => {
    const values = data.flatMap((s) => s.trail.flatMap((p) => [p.rs_ratio, p.rs_momentum]))
    const min = Math.min(100, ...values, 100)
    const max = Math.max(100, ...values, 100)
    const pad = Math.max((max - min) * 0.12, 1.5)
    return [min - pad, max + pad]
  }, [data])

  const quadrantGroups = useMemo(() => {
    const groups: Record<SectorRotationQuadrant, string[]> = {
      leading: [],
      weakening: [],
      lagging: [],
      improving: [],
    }
    for (const s of visibleData) groups[s.quadrant].push(s.sector)
    return groups
  }, [visibleData])

  const tableRows = useMemo(
    () =>
      [...data].sort(
        (a, b) => (b.trail.at(-1)?.rs_ratio ?? 0) - (a.trail.at(-1)?.rs_ratio ?? 0)
      ),
    [data]
  )

  const [domainMin, domainMax] = domain

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">
            Sector Rotation (RRG)
          </h2>
          <p className="text-xs text-zinc-500">
            JdK RS-Ratio vs. RS-Momentum against SPY — trails show each sector's last{' '}
            {data[0]?.trail.length ?? 10} {timeframe === 'weekly' ? 'weeks' : 'days'}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Timeframe">
          {TIMEFRAME_OPTIONS.map((option) => {
            const active = option.key === timeframe
            return (
              <button
                key={option.key}
                type="button"
                aria-pressed={active}
                onClick={() => setTimeframe(option.key)}
                className={`rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                  active
                    ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                    : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
                }`}
              >
                {option.label}
              </button>
            )
          })}
        </div>
      </div>

      {loading ? (
        <div className="h-96 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
      ) : error ? (
        <p className="text-sm text-red-500">Could not load sector rotation data.</p>
      ) : data.length === 0 ? (
        <p className="text-sm text-zinc-500">No sector rotation data available right now.</p>
      ) : (
        <>
          <div className="mb-2 flex flex-wrap gap-1.5" role="group" aria-label="Sectors">
            {data.map((s) => {
              const isHidden = hidden.has(s.sector)
              const style = getSectorStyle(s.sector)
              const color = getSectorChartColor(s.sector)
              return (
                <button
                  key={s.sector}
                  type="button"
                  aria-pressed={!isHidden}
                  onClick={() => toggleSector(s.sector)}
                  className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium transition-opacity ${
                    isHidden
                      ? 'border-zinc-200 text-zinc-400 opacity-50 dark:border-zinc-800'
                      : 'border-zinc-200 text-zinc-700 dark:border-zinc-700 dark:text-zinc-200'
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className="inline-block h-2 w-2 rounded-full"
                    style={{ backgroundColor: color }}
                  />
                  <span aria-hidden="true">{style.emoji}</span>
                  {s.etf}
                </button>
              )
            })}
          </div>

          <div className="h-96 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 8, right: 24, bottom: 24, left: 8 }}>
                <CartesianGrid stroke="currentColor" className="text-zinc-100 dark:text-zinc-800" />
                {QUADRANT_ORDER.map((quadrant) => {
                  const meta = QUADRANT_META[quadrant]
                  const isRight = quadrant === 'leading' || quadrant === 'weakening'
                  const isTop = quadrant === 'leading' || quadrant === 'improving'
                  return (
                    <ReferenceArea
                      key={quadrant}
                      x1={isRight ? 100 : domainMin}
                      x2={isRight ? domainMax : 100}
                      y1={isTop ? 100 : domainMin}
                      y2={isTop ? domainMax : 100}
                      fill={meta.wash}
                      fillOpacity={0.06}
                      stroke="none"
                      label={{
                        value: meta.label,
                        position: isTop
                          ? isRight
                            ? 'insideTopRight'
                            : 'insideTopLeft'
                          : isRight
                            ? 'insideBottomRight'
                            : 'insideBottomLeft',
                        fontSize: 10,
                        fontWeight: 600,
                        fill: 'currentColor',
                        className: 'text-zinc-400 dark:text-zinc-500',
                      }}
                    />
                  )
                })}
                <ReferenceLine x={100} stroke="currentColor" className="text-zinc-300 dark:text-zinc-700" />
                <ReferenceLine y={100} stroke="currentColor" className="text-zinc-300 dark:text-zinc-700" />
                <XAxis
                  type="number"
                  dataKey="rs_ratio"
                  domain={domain}
                  tick={{ fontSize: 11 }}
                  stroke="currentColor"
                  className="text-zinc-400"
                  tickLine={false}
                  label={{
                    value: 'JdK RS-Ratio',
                    position: 'insideBottom',
                    offset: -8,
                    fontSize: 11,
                    fill: 'currentColor',
                    className: 'text-zinc-500',
                  }}
                />
                <YAxis
                  type="number"
                  dataKey="rs_momentum"
                  domain={domain}
                  tick={{ fontSize: 11 }}
                  stroke="currentColor"
                  className="text-zinc-400"
                  tickLine={false}
                  label={{
                    value: 'JdK RS-Momentum',
                    angle: -90,
                    position: 'insideLeft',
                    fontSize: 11,
                    fill: 'currentColor',
                    className: 'text-zinc-500',
                  }}
                />
                <Tooltip content={<RRGTooltip />} cursor={{ strokeDasharray: '0' }} />
                {chartSeries.map((series) => (
                  <Scatter
                    key={series.sector}
                    data={series.points}
                    line={{ stroke: series.color, strokeWidth: 1.5, strokeOpacity: 0.6 }}
                    lineType="joint"
                    isAnimationActive={false}
                    shape={(props: unknown) => (
                      <SectorTrailDot {...(props as Partial<ChartPoint> & { cx?: number; cy?: number })} color={series.color} />
                    )}
                  />
                ))}
              </ScatterChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
            {QUADRANT_ORDER.map((quadrant) => {
              const meta = QUADRANT_META[quadrant]
              const sectors = quadrantGroups[quadrant]
              return (
                <div
                  key={quadrant}
                  data-testid={`quadrant-summary-${quadrant}`}
                  className="rounded-lg border border-zinc-100 p-2 dark:border-zinc-800"
                >
                  <div className={`text-[10px] font-semibold uppercase tracking-wide ${meta.badge}`}>
                    {meta.label}
                  </div>
                  {sectors.length === 0 ? (
                    <p className="mt-1 text-zinc-400">—</p>
                  ) : (
                    <ul className="mt-1 space-y-0.5">
                      {sectors.map((sector) => (
                        <li key={sector} className="flex items-center gap-1 text-zinc-600 dark:text-zinc-300">
                          <span aria-hidden="true">{getSectorStyle(sector).emoji}</span>
                          {sector}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )
            })}
          </div>

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
                    <th className="py-1">Sector</th>
                    <th className="py-1">ETF</th>
                    <th className="py-1 text-right">RS-Ratio</th>
                    <th className="py-1 text-right">RS-Momentum</th>
                    <th className="py-1 text-right">Quadrant</th>
                  </tr>
                </thead>
                <tbody>
                  {tableRows.map((s) => {
                    const latest = s.trail.at(-1)
                    const meta = QUADRANT_META[s.quadrant]
                    return (
                      <tr key={s.sector} className="border-t border-zinc-100 dark:border-zinc-900">
                        <td className="py-1">
                          {getSectorStyle(s.sector).emoji} {s.sector}
                        </td>
                        <td className="py-1 text-zinc-500">{s.etf}</td>
                        <td className="py-1 text-right font-mono tabular-nums">
                          {latest?.rs_ratio.toFixed(2) ?? '—'}
                        </td>
                        <td className="py-1 text-right font-mono tabular-nums">
                          {latest?.rs_momentum.toFixed(2) ?? '—'}
                        </td>
                        <td className={`py-1 text-right font-semibold ${meta.badge}`}>{meta.label}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
