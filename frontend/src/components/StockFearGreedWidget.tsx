import { useState } from 'react'
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useStockFearGreed } from '../hooks/useStockFearGreed'
import { useStockFearGreedHistory } from '../hooks/useStockFearGreedHistory'
import type { StockFearGreedWindow } from '../types'

const WINDOWS: Array<{ value: StockFearGreedWindow; label: string }> = [
  { value: 7, label: '7d' },
  { value: 30, label: '30d' },
]

const STATUS_COLOR: Record<string, string> = {
  'extreme fear': 'text-red-500',
  fear: 'text-orange-500',
  neutral: 'text-zinc-500 dark:text-zinc-400',
  greed: 'text-lime-500',
  'extreme greed': 'text-green-500',
}

function statusColor(status: string): string {
  return STATUS_COLOR[status.toLowerCase()] ?? 'text-zinc-500 dark:text-zinc-400'
}

function formatDay(date: string): string {
  const d = new Date(`${date}T00:00:00Z`)
  return Number.isNaN(d.getTime())
    ? date
    : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

function FearGreedHistoryChart({ days }: { days: StockFearGreedWindow }) {
  const { data, loading, error } = useStockFearGreedHistory(days)

  if (loading) {
    return <div className="h-24 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
  }
  if (error || !data || data.points.length < 2) {
    return <p className="text-xs text-zinc-500">History unavailable.</p>
  }

  const first = data.points[0].value
  const last = data.points[data.points.length - 1].value
  const color = last >= first ? '#34d399' : '#fb7185'

  return (
    <div className="h-24" data-testid="fear-greed-history">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data.points} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
          <defs>
            <linearGradient id="fearGreedFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="date" hide />
          <YAxis domain={[0, 100]} hide />
          <ReferenceLine y={50} stroke="#71717a" strokeDasharray="3 3" strokeOpacity={0.5} />
          <Tooltip
            formatter={(value) => [value, 'Index']}
            labelFormatter={(label) => formatDay(String(label))}
            contentStyle={{ fontSize: 12 }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            fill="url(#fearGreedFill)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
      <div className="mt-1 flex justify-between text-[11px] text-zinc-500">
        <span>{formatDay(data.points[0].date)}</span>
        <span>{formatDay(data.points[data.points.length - 1].date)}</span>
      </div>
    </div>
  )
}

export default function StockFearGreedWidget() {
  const { data, loading, error } = useStockFearGreed()
  const [days, setDays] = useState<StockFearGreedWindow>(30)

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">
          Stock Fear &amp; Greed Index
        </h2>
        <div className="flex rounded-lg border border-zinc-200 p-0.5 text-xs dark:border-zinc-800">
          {WINDOWS.map((w) => (
            <button
              key={w.value}
              type="button"
              onClick={() => setDays(w.value)}
              aria-pressed={days === w.value}
              className={`rounded-md px-2 py-0.5 ${
                days === w.value
                  ? 'bg-zinc-200 font-medium text-zinc-900 dark:bg-zinc-700 dark:text-zinc-100'
                  : 'text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'
              }`}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="h-10 w-32 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
      ) : error || !data ? (
        <p className="text-sm text-red-500">Could not load the Fear &amp; Greed index.</p>
      ) : (
        <div className="flex items-center space-x-4">
          <div className={`text-3xl font-bold ${statusColor(data.status)}`}>{data.value}</div>
          <div className="flex flex-col text-sm">
            <span className={`font-medium ${statusColor(data.status)}`}>{data.status}</span>
            {data.change && (
              <span
                className={
                  data.change.includes('+')
                    ? 'text-green-500'
                    : data.change.includes('-')
                      ? 'text-red-500'
                      : 'text-zinc-500'
                }
              >
                {data.change}
              </span>
            )}
          </div>
        </div>
      )}

      <div className="mt-3">
        <FearGreedHistoryChart days={days} />
      </div>
    </div>
  )
}
