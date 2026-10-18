import { usePutCallRatio } from '../hooks/usePutCallRatio'
import type { PutCallHistoryPoint, PutCallKey, PutCallRatio, PutCallSentiment } from '../types'

const BADGE_BASE = 'rounded-full px-2 py-0.5 text-[11px] font-semibold'

// A high equity ratio means traders are buying protection, a low one that
// they are chasing calls, so fear is drawn red and greed green.
const SENTIMENT: Record<PutCallSentiment, { label: string; className: string }> = {
  fear: { label: 'Fearful', className: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300' },
  neutral: { label: 'Neutral', className: 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300' },
  greed: {
    label: 'Complacent',
    className: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  },
}

const LABELS: Record<PutCallKey, string> = {
  total: 'Total',
  equity: 'Equity',
  index: 'Index',
  etp: 'ETPs',
  spx: 'SPX',
  vix: 'VIX',
}

const HEADLINE: PutCallKey[] = ['total', 'equity', 'index']

const LINE_COLORS = { total: '#38bdf8', equity: '#a78bfa' } as const // sky-400, violet-400

function fmtDate(iso: string): string {
  const parsed = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return iso
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function Change({ value }: { value: number | null }) {
  if (value == null) return null
  // Rising put/call is more hedging, so up reads as the bearish direction.
  const tone =
    value > 0
      ? 'text-rose-600 dark:text-rose-400'
      : value < 0
        ? 'text-emerald-600 dark:text-emerald-400'
        : 'text-zinc-500'
  return (
    <span className={`text-xs font-medium ${tone}`}>
      {value > 0 ? '+' : ''}
      {value.toFixed(2)}
    </span>
  )
}

function RatioTile({ ratio }: { ratio: PutCallRatio }) {
  return (
    <article className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
      <p className="text-[11px] uppercase tracking-wide text-zinc-500">{LABELS[ratio.key]}</p>
      <p className="flex items-baseline gap-2">
        <span className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">{ratio.value.toFixed(2)}</span>
        <Change value={ratio.change} />
      </p>
      {ratio.average != null && (
        <p className="text-[11px] text-zinc-500">20-day avg {ratio.average.toFixed(2)}</p>
      )}
    </article>
  )
}

function HistoryChart({
  history,
  thresholds,
}: {
  history: PutCallHistoryPoint[]
  thresholds: { fear: number; greed: number }
}) {
  const width = 320
  const height = 80
  const series = (['total', 'equity'] as const).map((key) => ({
    key,
    values: history.map((point) => point[key]),
  }))
  const all = series.flatMap((s) => s.values).filter((v): v is number => v != null)
  if (history.length < 2 || all.length === 0) return null
  const min = Math.min(...all, thresholds.greed) - 0.05
  const max = Math.max(...all, thresholds.fear) + 0.05
  const x = (i: number) => (i / (history.length - 1)) * width
  const y = (v: number) => height - ((v - min) / (max - min)) * height

  return (
    <div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-20 w-full"
        preserveAspectRatio="none"
        role="img"
        aria-label="Put/call ratio history"
      >
        {[thresholds.fear, thresholds.greed].map((level) => (
          <line
            key={level}
            x1={0}
            x2={width}
            y1={y(level)}
            y2={y(level)}
            stroke="currentColor"
            strokeDasharray="3 3"
            className="text-zinc-300 dark:text-zinc-700"
            vectorEffect="non-scaling-stroke"
          />
        ))}
        {series.map(({ key, values }) => (
          <polyline
            key={key}
            points={values
              .map((v, i) => (v == null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`))
              .filter(Boolean)
              .join(' ')}
            fill="none"
            stroke={LINE_COLORS[key]}
            strokeWidth={1.5}
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-[11px] text-zinc-500">
        <span>{fmtDate(history[0].date)}</span>
        <span className="flex items-center gap-3">
          {series.map(({ key }) => (
            <span key={key} className="flex items-center gap-1">
              <span className="inline-block h-0.5 w-3" style={{ backgroundColor: LINE_COLORS[key] }} />
              {LABELS[key]}
            </span>
          ))}
          <span>
            Dashed: equity {thresholds.greed.toFixed(2)} / {thresholds.fear.toFixed(2)}
          </span>
        </span>
        <span>{fmtDate(history[history.length - 1].date)}</span>
      </div>
    </div>
  )
}

export default function PutCallRatioWidget() {
  const { data, loading, error } = usePutCallRatio()

  const headline = HEADLINE.map((key) => data?.ratios.find((r) => r.key === key)).filter(
    (r): r is PutCallRatio => r != null,
  )
  const secondary = (data?.ratios ?? []).filter((r) => !HEADLINE.includes(r.key))
  const sentiment = data?.sentiment ? SENTIMENT[data.sentiment] : null

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Put/Call Ratio</h2>
          {data?.date && <p className="text-[11px] text-zinc-500">Cboe, session of {fmtDate(data.date)}</p>}
        </div>
        {sentiment && (
          <span className={`${BADGE_BASE} ${sentiment.className}`} title="From the equity put/call ratio">
            {sentiment.label}
          </span>
        )}
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-8 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load put/call ratios.</p>
      ) : headline.length === 0 ? (
        <p className="text-sm text-zinc-500">No Cboe session data available right now.</p>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            {headline.map((ratio) => (
              <RatioTile key={ratio.key} ratio={ratio} />
            ))}
          </div>
          {secondary.length > 0 && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-600 dark:text-zinc-300">
              {secondary.map((ratio) => (
                <span key={ratio.key}>
                  <span className="text-zinc-500">{LABELS[ratio.key]}</span>{' '}
                  <span className="font-semibold">{ratio.value.toFixed(2)}</span>{' '}
                  <Change value={ratio.change} />
                </span>
              ))}
            </div>
          )}
          {data && <HistoryChart history={data.history} thresholds={data.thresholds} />}
        </div>
      )}
    </div>
  )
}
