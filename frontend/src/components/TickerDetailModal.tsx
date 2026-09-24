import { useEffect, useState } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useTickerPriceHistory } from '../hooks/useTickerPriceHistory'
import { useTickerTimeseries } from '../hooks/useTickerTimeseries'
import type { TickerPriceHistoryPoint, TickerTimeseriesPoint } from '../types'

const MENTIONS_COLOR = '#6366f1' // indigo-500
const BULL_COLOR = '#10b981' // emerald-500
const BEAR_COLOR = '#f43f5e' // rose-500
const NEUTRAL_COLOR = '#a1a1aa' // zinc-400
// Same pair the Sparkline component uses, so a ticker's price line always
// matches the % badge sitting next to it exactly - not just in the same
// direction, but the same literal color (Tailwind's separate light/dark
// text-emerald-600/text-emerald-400 classes render visibly different
// shades than a chart line drawn with a single fixed color).
const PRICE_UP_COLOR = '#34d399' // emerald-400
const PRICE_DOWN_COLOR = '#fb7185' // rose-400

type TickerDetailModalProps = {
  ticker: string
  onClose: () => void
}

type WindowOption = { value: number; label: string }

const WINDOWS: WindowOption[] = [
  { value: 24, label: '24h' },
  { value: 168, label: '7d' },
  { value: 720, label: '30d' },
]

function formatBucket(bucket: string, bucketHours: number): string {
  const parsed = new Date(bucket)
  if (Number.isNaN(parsed.getTime())) return bucket
  if (bucketHours >= 24) {
    return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  }
  return parsed.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
  })
}

function pct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function sentimentTone(label: string | null | undefined): string {
  if (label === 'BULL') return 'text-emerald-600 dark:text-emerald-400'
  if (label === 'BEAR') return 'text-rose-600 dark:text-rose-400'
  return 'text-zinc-500 dark:text-zinc-400'
}

function formatIntradayTick(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

function fmtPricePoint(value: number): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: value < 1 ? 4 : 2,
    maximumFractionDigits: value < 1 ? 4 : 2,
  })
}

function PriceTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: Array<{ payload: TickerPriceHistoryPoint }>
}) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload
  return (
    <div className="rounded-lg border border-zinc-200 bg-white/95 px-3 py-2 text-xs shadow-lg dark:border-zinc-700 dark:bg-zinc-900/95">
      <div className="font-semibold text-zinc-700 dark:text-zinc-200">
        {formatIntradayTick(point.t)}
      </div>
      <div className="mt-1 font-mono text-zinc-900 dark:text-zinc-100">
        ${fmtPricePoint(point.close)}
      </div>
    </div>
  )
}

function MentionsTooltip({
  active,
  payload,
  bucketHours,
}: {
  active?: boolean
  payload?: Array<{ payload: TickerTimeseriesPoint }>
  bucketHours: number
}) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload
  return (
    <div className="rounded-lg border border-zinc-200 bg-white/95 px-3 py-2 text-xs shadow-lg dark:border-zinc-700 dark:bg-zinc-900/95">
      <div className="font-semibold text-zinc-700 dark:text-zinc-200">
        {formatBucket(point.bucket, bucketHours)}
      </div>
      <div className="mt-1 font-mono text-zinc-900 dark:text-zinc-100">
        {point.mentions} mentions
      </div>
      <div className="mt-1 flex gap-2 font-mono text-[11px]">
        <span className="text-emerald-600 dark:text-emerald-400">{point.bullish} bull</span>
        <span className="text-rose-600 dark:text-rose-400">{point.bearish} bear</span>
        <span className="text-zinc-500 dark:text-zinc-400">{point.neutral} neutral</span>
      </div>
    </div>
  )
}

export default function TickerDetailModal({ ticker, onClose }: TickerDetailModalProps) {
  const [windowHours, setWindowHours] = useState(168)
  const { data, loading, error } = useTickerTimeseries(ticker, windowHours)
  const {
    data: priceData,
    loading: priceLoading,
    error: priceError,
  } = useTickerPriceHistory(ticker)

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const points = data?.points ?? []
  const summary = data?.summary

  const pricePoints = priceData?.points ?? []
  const priceChangePct =
    pricePoints.length >= 2
      ? ((pricePoints[pricePoints.length - 1].close - pricePoints[0].close) /
          pricePoints[0].close) *
        100
      : null
  // Line color follows its own start-to-end movement (like the macro strip
  // sparkline), not some other day-change metric - so it never contradicts
  // the direction it visibly draws.
  const priceColor = (priceChangePct ?? 0) < 0 ? PRICE_DOWN_COLOR : PRICE_UP_COLOR
  const bucketHours = data?.bucket_hours ?? 1

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`$${ticker} details`}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-zinc-200 bg-white p-5 shadow-xl dark:border-zinc-800 dark:bg-zinc-950"
        onClick={(ev) => ev.stopPropagation()}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              ${ticker}
            </h2>
            <p className="text-xs text-zinc-500">
              Today's price, plus mentions and sentiment from the tracked tweet history.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1" role="group" aria-label="Timeseries window">
              {WINDOWS.map((w) => (
                <button
                  key={w.value}
                  type="button"
                  onClick={() => setWindowHours(w.value)}
                  aria-pressed={w.value === windowHours}
                  className={`rounded-md px-2 py-1 text-[11px] font-semibold transition-colors ${
                    w.value === windowHours
                      ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                      : 'border border-zinc-300 text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800'
                  }`}
                >
                  {w.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close ticker details"
              className="rounded-full bg-zinc-900 px-3 py-1 text-xs font-semibold text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
            >
              Close
            </button>
          </div>
        </div>

        <div className="mt-4">
          <div className="flex items-baseline justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Price today
            </h3>
            {priceChangePct != null && (
              <span className="font-mono text-xs font-semibold" style={{ color: priceColor }}>
                {pct(priceChangePct)}
              </span>
            )}
          </div>
          <div className="mt-2 h-40 w-full">
            {priceLoading ? (
              <div className="h-full w-full animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
            ) : priceError || pricePoints.length < 2 ? (
              <div className="flex h-full items-center justify-center rounded-lg bg-zinc-50 text-xs text-zinc-500 dark:bg-zinc-900">
                No intraday price data available for ${ticker}.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={pricePoints} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="ticker-price-fill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={priceColor} stopOpacity={0.28} />
                      <stop offset="100%" stopColor={priceColor} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    stroke="currentColor"
                    className="text-zinc-200 dark:text-zinc-800"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="t"
                    tickFormatter={formatIntradayTick}
                    tick={{ fontSize: 11 }}
                    stroke="currentColor"
                    className="text-zinc-400"
                    minTickGap={48}
                    tickLine={false}
                  />
                  <YAxis
                    domain={['auto', 'auto']}
                    tick={{ fontSize: 11 }}
                    stroke="currentColor"
                    className="text-zinc-400"
                    width={52}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={fmtPricePoint}
                  />
                  <Tooltip content={<PriceTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="close"
                    name="Price"
                    stroke={priceColor}
                    strokeWidth={2}
                    fill="url(#ticker-price-fill)"
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {error && (
          <p className="mt-3 text-sm text-rose-500">Failed to load ${ticker} details.</p>
        )}

        {loading ? (
          <div className="mt-4 space-y-3">
            <div className="h-20 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
            <div className="h-48 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
            <div className="h-32 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
          </div>
        ) : !summary || summary.total_mentions === 0 ? (
          <p className="mt-6 py-6 text-center text-sm text-zinc-500">
            No ${ticker} mentions in the last {WINDOWS.find((w) => w.value === windowHours)?.label}.
          </p>
        ) : (
          <>
            <div className="mt-4 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
              <div className="rounded-xl bg-zinc-100/80 p-2 dark:bg-zinc-800/70">
                <p className="text-zinc-500">Total mentions</p>
                <p className="mt-0.5 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                  {summary.total_mentions}
                </p>
              </div>
              <div className="rounded-xl bg-zinc-100/80 p-2 dark:bg-zinc-800/70">
                <p className="text-zinc-500">Avg mentions / bucket</p>
                <p className="mt-0.5 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                  {summary.avg_mentions_per_bucket.toFixed(1)}
                </p>
              </div>
              <div className="rounded-xl bg-zinc-100/80 p-2 dark:bg-zinc-800/70">
                <p className="text-zinc-500">Overall sentiment</p>
                <p className={`mt-0.5 text-sm font-semibold ${sentimentTone(summary.sentiment_label)}`}>
                  {summary.sentiment_label} ({summary.bullish}🐂 / {summary.bearish}🐻)
                </p>
              </div>
              <div className="rounded-xl bg-zinc-100/80 p-2 dark:bg-zinc-800/70">
                <p className="text-zinc-500">Price move</p>
                <p
                  className={`mt-0.5 text-sm font-semibold ${
                    (summary.price_direction ?? 0) >= 0
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : 'text-rose-600 dark:text-rose-400'
                  }`}
                >
                  {pct(summary.price_direction)}
                </p>
              </div>
              <div className="rounded-xl bg-zinc-100/80 p-2 dark:bg-zinc-800/70">
                <p className="text-zinc-500">Unique voices</p>
                <p className="mt-0.5 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                  {summary.unique_authors}
                </p>
              </div>
              <div className="rounded-xl bg-zinc-100/80 p-2 dark:bg-zinc-800/70">
                <p className="text-zinc-500">Chart-tagged tweets</p>
                <p className="mt-0.5 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                  {summary.chart_mentions}
                </p>
              </div>
              <div className="rounded-xl bg-zinc-100/80 p-2 dark:bg-zinc-800/70">
                <p className="text-zinc-500">Avg engagement</p>
                <p className="mt-0.5 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                  {summary.avg_engagement != null ? summary.avg_engagement.toFixed(0) : '—'}
                </p>
              </div>
              <div className="rounded-xl bg-zinc-100/80 p-2 dark:bg-zinc-800/70">
                <p className="text-zinc-500">Asset kind</p>
                <p className="mt-0.5 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                  {summary.asset_kind ?? '—'}
                </p>
              </div>
            </div>

            <div className="mt-5">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Mentions over time
              </h3>
              <div className="mt-2 h-48 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                    <defs>
                      <linearGradient id="ticker-mentions-fill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={MENTIONS_COLOR} stopOpacity={0.28} />
                        <stop offset="100%" stopColor={MENTIONS_COLOR} stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid
                      stroke="currentColor"
                      className="text-zinc-200 dark:text-zinc-800"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="bucket"
                      tickFormatter={(value: string) => formatBucket(value, bucketHours)}
                      tick={{ fontSize: 11 }}
                      stroke="currentColor"
                      className="text-zinc-400"
                      minTickGap={32}
                      tickLine={false}
                    />
                    <YAxis
                      allowDecimals={false}
                      tick={{ fontSize: 11 }}
                      stroke="currentColor"
                      className="text-zinc-400"
                      width={32}
                      tickLine={false}
                      axisLine={false}
                    />
                    <Tooltip content={<MentionsTooltip bucketHours={bucketHours} />} />
                    <ReferenceLine
                      y={summary.avg_mentions_per_bucket}
                      stroke="currentColor"
                      className="text-zinc-400"
                      strokeDasharray="4 4"
                      label={{
                        value: 'Avg',
                        position: 'insideTopLeft',
                        fontSize: 10,
                        fill: 'currentColor',
                        className: 'text-zinc-500',
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="mentions"
                      name="Mentions"
                      stroke={MENTIONS_COLOR}
                      strokeWidth={2}
                      fill="url(#ticker-mentions-fill)"
                      isAnimationActive={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="mt-5">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Bullish vs bearish mentions
              </h3>
              <div className="mt-2 h-40 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                    <CartesianGrid
                      stroke="currentColor"
                      className="text-zinc-200 dark:text-zinc-800"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="bucket"
                      tickFormatter={(value: string) => formatBucket(value, bucketHours)}
                      tick={{ fontSize: 11 }}
                      stroke="currentColor"
                      className="text-zinc-400"
                      minTickGap={32}
                      tickLine={false}
                    />
                    <YAxis
                      allowDecimals={false}
                      tick={{ fontSize: 11 }}
                      stroke="currentColor"
                      className="text-zinc-400"
                      width={32}
                      tickLine={false}
                      axisLine={false}
                    />
                    <Tooltip content={<MentionsTooltip bucketHours={bucketHours} />} />
                    <Bar dataKey="bullish" name="Bullish" stackId="sentiment" fill={BULL_COLOR} isAnimationActive={false} />
                    <Bar dataKey="bearish" name="Bearish" stackId="sentiment" fill={BEAR_COLOR} isAnimationActive={false} />
                    <Bar dataKey="neutral" name="Neutral" stackId="sentiment" fill={NEUTRAL_COLOR} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
