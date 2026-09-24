import { useMemo, useState } from 'react'
import {
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  usePlotArea,
  useXAxisScale,
  useYAxisScale,
} from 'recharts'
import { useSectorRotation } from '../hooks/useSectorRotation'
import type {
  SectorRotationPoint,
  SectorRotationQuadrant,
  SectorRotationSeries,
  SectorRotationTimeframe,
} from '../types'
import { placeLabels, rrgDomain, type PlacedLabel } from '../utils/rrgLayout'
import { getSectorChartColor, getSectorStyle } from '../utils/sectorStyle'

const TIMEFRAME_OPTIONS: Array<{ key: SectorRotationTimeframe; label: string }> = [
  { key: 'daily', label: 'Daily' },
  { key: 'weekly', label: 'Weekly' },
]

type TailLength = number | 'full'

const SHORT_TAIL = 5

const TAIL_OPTIONS: Array<{ key: TailLength; label: string }> = [
  { key: SHORT_TAIL, label: 'Short tail' },
  { key: 'full', label: 'Full tail' },
]

function SegmentedControl<T extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: Array<{ key: T; label: string }>
  value: T
  onChange: (key: T) => void
}) {
  return (
    <div className="flex rounded-full bg-zinc-100 p-0.5 dark:bg-zinc-800" role="group" aria-label={label}>
      {options.map((option) => {
        const active = option.key === value
        return (
          <button
            key={String(option.key)}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.key)}
            className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold transition-colors ${
              active
                ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-600 dark:text-zinc-50'
                : 'text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200'
            }`}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

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
}

type Series = {
  sector: string
  etf: string
  color: string
  points: ChartPoint[]
}

function gradientId(sector: string) {
  return `rrg-tail-${sector.replace(/[^a-z0-9]/gi, '-')}`
}

/** Polyline through the points with the corners rounded off (midpoint quadratic curves). */
function smoothPath(points: Array<{ x: number; y: number }>): string {
  if (points.length < 3) return points.map((p, i) => `${i ? 'L' : 'M'}${p.x},${p.y}`).join(' ')
  let d = `M${points[0].x},${points[0].y}`
  for (let i = 1; i < points.length - 1; i++) {
    const mx = (points[i].x + points[i + 1].x) / 2
    const my = (points[i].y + points[i + 1].y) / 2
    d += ` Q${points[i].x},${points[i].y} ${mx},${my}`
  }
  const last = points[points.length - 1]
  return `${d} L${last.x},${last.y}`
}

/** Invisible hover target; the visible marks are drawn by {@link RRGOverlay}. */
function HitTarget({ cx, cy }: { cx?: number; cy?: number }) {
  if (cx == null || cy == null) return null
  return <circle cx={cx} cy={cy} r={8} fill="transparent" />
}

/**
 * Draws every trail, head dot and label in pixel space, so labels can be
 * de-collided against each other (Recharts' per-point labels can't see their
 * neighbours). Non-interactive; hover is handled by the Scatter hit targets.
 */
function RRGOverlay({ series, focus }: { series: Series[]; focus: string | null }) {
  const xScale = useXAxisScale()
  const yScale = useYAxisScale()
  const plot = usePlotArea()

  const projected = useMemo(() => {
    if (!xScale || !yScale) return []
    return series.map((s) => ({
      ...s,
      pixels: s.points.map((p) => ({ x: xScale(p.rs_ratio) ?? 0, y: yScale(p.rs_momentum) ?? 0 })),
    }))
  }, [series, xScale, yScale])

  const labels = useMemo(() => {
    if (!plot) return new Map<string, PlacedLabel>()
    const anchors = projected
      .filter((s) => s.pixels.length > 0)
      .map((s) => ({ id: s.sector, text: s.etf, ...s.pixels[s.pixels.length - 1] }))
    const trailPoints = projected.flatMap((s) => s.pixels.slice(0, -1))
    return new Map(placeLabels(anchors, plot, trailPoints).map((l) => [l.id, l]))
  }, [projected, plot])

  if (!projected.length) return null

  // Focused sector last, so it paints above the dimmed ones.
  const ordered = focus
    ? [...projected.filter((s) => s.sector !== focus), ...projected.filter((s) => s.sector === focus)]
    : projected

  return (
    <g pointerEvents="none">
      {ordered.map((s) => {
        const dimmed = focus != null && focus !== s.sector
        const focused = focus === s.sector
        const head = s.pixels[s.pixels.length - 1]
        const label = labels.get(s.sector)
        if (!head) return null
        return (
          <g key={s.sector} opacity={dimmed ? 0.15 : 1} data-sector={s.sector}>
            {s.pixels.length > 1 && (
              <>
                <defs>
                  <linearGradient
                    id={gradientId(s.sector)}
                    gradientUnits="userSpaceOnUse"
                    x1={s.pixels[0].x}
                    y1={s.pixels[0].y}
                    x2={head.x}
                    y2={head.y}
                  >
                    <stop offset="0%" stopColor={s.color} stopOpacity={0.1} />
                    <stop offset="100%" stopColor={s.color} stopOpacity={0.9} />
                  </linearGradient>
                </defs>
                <path
                  d={smoothPath(s.pixels)}
                  fill="none"
                  stroke={`url(#${gradientId(s.sector)})`}
                  strokeWidth={focused ? 2.5 : 1.75}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </>
            )}
            {focused &&
              s.pixels
                .slice(0, -1)
                .map((p, i) => <circle key={i} cx={p.x} cy={p.y} r={2} fill={s.color} fillOpacity={0.7} />)}
            <circle
              cx={head.x}
              cy={head.y}
              r={focused ? 6.5 : 5}
              fill={s.color}
              stroke="currentColor"
              strokeWidth={1.5}
              className="text-white dark:text-zinc-900"
            />
            {label && (
              <>
                {label.displaced && (
                  <line
                    x1={head.x}
                    y1={head.y}
                    x2={Math.min(Math.max(head.x, label.x), label.x + label.width)}
                    y2={Math.min(Math.max(head.y, label.y), label.y + label.height)}
                    stroke="currentColor"
                    strokeWidth={0.75}
                    className="text-zinc-400 dark:text-zinc-600"
                  />
                )}
                <text
                  x={label.x + 1}
                  y={label.y + label.height - 2.5}
                  fontSize={10}
                  fontWeight={focused ? 700 : 600}
                  fill="currentColor"
                  className="text-zinc-700 dark:text-zinc-200"
                >
                  {s.etf}
                </text>
              </>
            )}
          </g>
        )
      })}
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
  const [tail, setTail] = useState<TailLength>(SHORT_TAIL)
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [focus, setFocus] = useState<string | null>(null)
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

  const trimmed = useMemo(
    () =>
      data.map((s) => ({
        ...s,
        trail: tail === 'full' ? s.trail : s.trail.slice(-tail),
      })),
    [data, tail]
  )

  const chartSeries = useMemo<Series[]>(
    () =>
      trimmed
        .filter((s) => !hidden.has(s.sector))
        .map((s) => ({
          sector: s.sector,
          etf: s.etf,
          color: getSectorChartColor(s.sector),
          points: s.trail.map((p) => ({ ...p, sector: s.sector, etf: s.etf, quadrant: s.quadrant })),
        })),
    [trimmed, hidden]
  )

  // From every sector (hidden or not) so toggling one doesn't rescale the chart.
  const { domain, ticks } = useMemo(
    () => rrgDomain(trimmed.flatMap((s) => s.trail.flatMap((p) => [p.rs_ratio, p.rs_momentum]))),
    [trimmed]
  )

  const quadrantGroups = useMemo(() => {
    const groups: Record<SectorRotationQuadrant, SectorRotationSeries[]> = {
      leading: [],
      weakening: [],
      lagging: [],
      improving: [],
    }
    for (const s of data) groups[s.quadrant].push(s)
    for (const list of Object.values(groups)) {
      list.sort((a, b) => (b.trail.at(-1)?.rs_ratio ?? 0) - (a.trail.at(-1)?.rs_ratio ?? 0))
    }
    return groups
  }, [data])

  const tableRows = useMemo(
    () =>
      [...data].sort(
        (a, b) => (b.trail.at(-1)?.rs_ratio ?? 0) - (a.trail.at(-1)?.rs_ratio ?? 0)
      ),
    [data]
  )

  const [domainMin, domainMax] = domain
  const fullLength = data[0]?.trail.length ?? 0
  const shownLength = tail === 'full' ? fullLength : Math.min(tail, fullLength)
  const unit = timeframe === 'weekly' ? 'weeks' : 'days'

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">
            Sector Rotation (RRG)
          </h2>
          <p className="text-xs text-zinc-500">
            Relative strength vs. SPY · tails show the last {shownLength || '—'} {unit}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <SegmentedControl
            label="Tail length"
            options={TAIL_OPTIONS}
            value={tail}
            onChange={setTail}
          />
          <SegmentedControl
            label="Timeframe"
            options={TIMEFRAME_OPTIONS}
            value={timeframe}
            onChange={setTimeframe}
          />
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
          <div className="h-96 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 8, right: 16, bottom: 20, left: 0 }}>
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
                      fillOpacity={0.05}
                      stroke="none"
                      label={{
                        value: meta.label.toUpperCase(),
                        position: isTop
                          ? isRight
                            ? 'insideTopRight'
                            : 'insideTopLeft'
                          : isRight
                            ? 'insideBottomRight'
                            : 'insideBottomLeft',
                        fontSize: 10,
                        fontWeight: 700,
                        letterSpacing: 0.5,
                        fill: meta.wash,
                        fillOpacity: 0.7,
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
                  ticks={ticks}
                  allowDataOverflow
                  tick={{ fontSize: 10 }}
                  stroke="currentColor"
                  className="text-zinc-400"
                  axisLine={false}
                  tickLine={false}
                  label={{
                    value: 'RS-Ratio →',
                    position: 'insideBottom',
                    offset: -12,
                    fontSize: 10,
                    fill: 'currentColor',
                    className: 'text-zinc-500',
                  }}
                />
                <YAxis
                  type="number"
                  dataKey="rs_momentum"
                  domain={domain}
                  ticks={ticks}
                  allowDataOverflow
                  width={44}
                  tick={{ fontSize: 10 }}
                  stroke="currentColor"
                  className="text-zinc-400"
                  axisLine={false}
                  tickLine={false}
                  label={{
                    value: 'RS-Momentum →',
                    angle: -90,
                    position: 'insideLeft',
                    offset: 4,
                    fontSize: 10,
                    fill: 'currentColor',
                    className: 'text-zinc-500',
                  }}
                />
                <RRGOverlay series={chartSeries} focus={focus} />
                <Tooltip content={<RRGTooltip />} cursor={false} />
                {chartSeries.map((series) => (
                  <Scatter
                    key={series.sector}
                    data={series.points}
                    isAnimationActive={false}
                    shape={HitTarget}
                    onMouseEnter={() => setFocus(series.sector)}
                    onMouseLeave={() => setFocus(null)}
                  />
                ))}
              </ScatterChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4" role="group" aria-label="Sectors">
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
                      {sectors.map((s) => {
                        const isHidden = hidden.has(s.sector)
                        return (
                          <li key={s.sector}>
                            <button
                              type="button"
                              aria-pressed={!isHidden}
                              title={isHidden ? `Show ${s.sector}` : `Hide ${s.sector}`}
                              onClick={() => toggleSector(s.sector)}
                              onMouseEnter={() => !isHidden && setFocus(s.sector)}
                              onMouseLeave={() => setFocus(null)}
                              onFocus={() => !isHidden && setFocus(s.sector)}
                              onBlur={() => setFocus(null)}
                              className={`flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left transition-opacity hover:bg-zinc-50 dark:hover:bg-zinc-800/60 ${
                                isHidden ? 'opacity-40' : ''
                              }`}
                            >
                              <span
                                aria-hidden="true"
                                className="inline-block h-2 w-2 shrink-0 rounded-full"
                                style={{ backgroundColor: getSectorChartColor(s.sector) }}
                              />
                              <span className="w-9 shrink-0 font-semibold text-zinc-700 dark:text-zinc-200">
                                {s.etf}
                              </span>
                              <span className="truncate text-zinc-500">{s.sector}</span>
                            </button>
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </div>
              )
            })}
          </div>

          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-zinc-500">
            <button
              type="button"
              onClick={() => setShowTable((open) => !open)}
              className="font-semibold underline underline-offset-2 hover:text-zinc-700 dark:hover:text-zinc-300"
            >
              {showTable ? 'Hide table view' : 'Show table view'}
            </button>
            <span>Hover a sector to highlight it · click to hide</span>
          </div>

          {showTable && (
            <div className="mt-2 max-h-56 overflow-auto">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-white text-zinc-500 dark:bg-zinc-900">
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
                      <tr key={s.sector} className="border-t border-zinc-100 dark:border-zinc-800">
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
