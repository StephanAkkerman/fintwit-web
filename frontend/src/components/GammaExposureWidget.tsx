import { useMemo } from 'react'
import {
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useGammaExposure } from '../hooks/useGammaExposure'
import type { GammaExposureHistoryPoint, GammaRegime } from '../types'

const POSITIVE = '#10b981' // emerald-500 -- same up/bullish color as PortfolioValueChart
const NEGATIVE = '#f43f5e' // rose-500 -- same down/bearish color as PortfolioValueChart

function formatGex(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'N/A'
  const abs = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(2)}K`
  return `${sign}$${abs.toFixed(0)}`
}

function formatPrice(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'N/A'
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

type ChartPoint = { ts: number; spot_price: number; regime: GammaRegime }

function toChartPoints(history: GammaExposureHistoryPoint[]): ChartPoint[] {
  return history
    .map((point) => ({
      ts: new Date(point.captured_at).getTime(),
      spot_price: point.spot_price,
      regime: point.regime,
    }))
    .filter((point) => Number.isFinite(point.ts))
    .sort((a, b) => a.ts - b.ts)
}

/** Contiguous runs of the same regime, so each can be drawn as one shaded band. */
function regimeSegments(points: ChartPoint[]): Array<{ x1: number; x2: number; regime: GammaRegime }> {
  if (points.length === 0) return []

  const segments: Array<{ x1: number; x2: number; regime: GammaRegime }> = []
  let start = points[0]
  let prev = points[0]

  for (let i = 1; i < points.length; i++) {
    const point = points[i]
    if (point.regime !== prev.regime) {
      segments.push({ x1: start.ts, x2: point.ts, regime: prev.regime })
      start = point
    }
    prev = point
  }
  segments.push({ x1: start.ts, x2: prev.ts, regime: prev.regime })
  return segments
}

function RegimeBadge({ regime }: { regime: GammaRegime }) {
  const isPositive = regime === 'positive'
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
        isPositive
          ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
          : 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
      }`}
    >
      {isPositive ? 'Positive Gamma' : 'Negative Gamma'}
    </span>
  )
}

function GammaTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: Array<{ payload: ChartPoint }>
}) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload

  return (
    <div className="rounded-lg border border-zinc-200 bg-white/95 px-3 py-2 text-xs shadow-lg dark:border-zinc-700 dark:bg-zinc-900/95">
      <div className="font-semibold text-zinc-700 dark:text-zinc-200">{formatTime(point.ts)}</div>
      <div className="mt-1 font-mono text-sm text-zinc-900 dark:text-zinc-100">
        {formatPrice(point.spot_price)}
      </div>
      <div
        className={
          point.regime === 'positive'
            ? 'font-semibold text-emerald-600 dark:text-emerald-400'
            : 'font-semibold text-rose-600 dark:text-rose-400'
        }
      >
        {point.regime === 'positive' ? 'Positive gamma' : 'Negative gamma'}
      </div>
    </div>
  )
}

export default function GammaExposureWidget({ symbol = 'SPY' }: { symbol?: string }) {
  const { snapshot, history, loading, error } = useGammaExposure(symbol)

  const chartPoints = useMemo(() => toChartPoints(history), [history])
  const segments = useMemo(() => regimeSegments(chartPoints), [chartPoints])

  const domain = useMemo<[number, number]>(() => {
    if (chartPoints.length === 0) return [0, 1]
    const values = chartPoints.map((p) => p.spot_price)
    const min = Math.min(...values)
    const max = Math.max(...values)
    const pad = (max - min || Math.abs(max) || 1) * 0.1
    return [min - pad, max + pad]
  }, [chartPoints])

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">
          {symbol} Gamma Exposure
        </h2>
        {!loading && !error && <RegimeBadge regime={snapshot.regime} />}
      </div>

      {loading ? (
        <div className="space-y-2">
          <div className="h-8 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
          <div className="h-48 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load gamma exposure data.</p>
      ) : (
        <>
          <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <article className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">Spot</p>
              <p className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
                {formatPrice(snapshot.spot_price)}
              </p>
            </article>
            <article className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">Net GEX</p>
              <p
                className={`text-base font-semibold ${
                  snapshot.net_gex >= 0
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-rose-600 dark:text-rose-400'
                }`}
              >
                {formatGex(snapshot.net_gex)}
              </p>
            </article>
            <article className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">Zero Gamma</p>
              <p className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
                {snapshot.flip_point == null ? 'N/A' : formatPrice(snapshot.flip_point)}
              </p>
            </article>
            <article className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">Call / Put GEX</p>
              <p className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
                {formatGex(snapshot.call_gex)} / {formatGex(snapshot.put_gex)}
              </p>
            </article>
          </div>

          {chartPoints.length < 2 ? (
            <p className="py-6 text-center text-sm text-zinc-500">
              Regime history builds up as snapshots are recorded — check back later to see it
              plotted over price.
            </p>
          ) : (
            <div className="h-56 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartPoints} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                  {segments.map((segment) => (
                    <ReferenceArea
                      key={`${segment.x1}-${segment.x2}`}
                      x1={segment.x1}
                      x2={segment.x2}
                      fill={segment.regime === 'positive' ? POSITIVE : NEGATIVE}
                      fillOpacity={0.12}
                      strokeOpacity={0}
                      ifOverflow="extendDomain"
                    />
                  ))}
                  <XAxis
                    dataKey="ts"
                    type="number"
                    domain={['dataMin', 'dataMax']}
                    tickFormatter={formatTime}
                    tick={{ fontSize: 11 }}
                    stroke="currentColor"
                    className="text-zinc-400"
                    minTickGap={48}
                    tickLine={false}
                  />
                  <YAxis
                    domain={domain}
                    tickFormatter={(value: number) => value.toFixed(0)}
                    tick={{ fontSize: 11 }}
                    stroke="currentColor"
                    className="text-zinc-400"
                    width={56}
                    tickLine={false}
                    axisLine={false}
                  />
                  <Tooltip
                    content={<GammaTooltip />}
                    cursor={{ stroke: 'currentColor', strokeWidth: 1, className: 'text-zinc-400' }}
                  />
                  {snapshot.flip_point != null && (
                    <ReferenceLine
                      y={snapshot.flip_point}
                      stroke="currentColor"
                      className="text-zinc-400"
                      strokeDasharray="4 4"
                      label={{
                        value: 'Zero gamma',
                        position: 'insideTopLeft',
                        fontSize: 10,
                        fill: 'currentColor',
                        className: 'text-zinc-500',
                      }}
                    />
                  )}
                  <Line
                    type="monotone"
                    dataKey="spot_price"
                    name="Spot price"
                    stroke="currentColor"
                    className="text-zinc-700 dark:text-zinc-200"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          <p className="mt-3 text-[11px] text-zinc-400">
            Estimated from the free {snapshot.symbol} options chain (Black-Scholes gamma × open
            interest), not real dealer positioning — treat the regime as directional, not exact.
            Shaded bands mark negative-gamma stretches, when dealer hedging is expected to
            amplify moves rather than dampen them.
          </p>
        </>
      )}
    </div>
  )
}
