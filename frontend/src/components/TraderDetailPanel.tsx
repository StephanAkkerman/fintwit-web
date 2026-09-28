import { useMemo } from 'react'
import {
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useTraderDetail } from '../hooks/useTraderDetail'
import type { TraderCall, TraderCallHorizon, TraderCallResult, TraderTickerStat } from '../types'
import { formatReturnPct, hitRateClass, returnClass, signedReturn } from '../utils/traderFormat'

type Props = {
  screenName: string
  horizon: TraderCallHorizon
  onClose: () => void
  onTickerClick?: (ticker: string) => void
}

type ChartPoint = {
  t: number
  ret: number
  ticker: string
  direction: TraderCall['direction']
  correct: boolean
}

const WIN_COLOR = '#10b981'
const LOSS_COLOR = '#f43f5e'

/** Backend timestamps are naive UTC (`2026-09-28 14:03:00`). */
function parseUtc(value: string | null | undefined): Date | null {
  if (!value) return null
  const iso = value.includes('T') ? value : value.replace(' ', 'T')
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`)
  return Number.isNaN(d.getTime()) ? null : d
}

function formatDate(value: string | null | undefined): string {
  const d = parseUtc(value)
  return d ? d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—'
}

function formatDateTime(value: string | null | undefined): string {
  const d = parseUtc(value)
  return d
    ? d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : '—'
}

function formatPrice(value: number | null | undefined): string {
  if (value == null) return '—'
  const abs = Math.abs(value)
  const digits = abs >= 1000 ? 0 : abs >= 1 ? 2 : abs >= 0.01 ? 4 : 8
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: Math.min(digits, 2) })}`
}

function DirectionPill({ direction }: { direction: TraderCall['direction'] }) {
  const bullish = direction === 'bullish'
  return (
    <span
      className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
        bullish
          ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400'
          : 'bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400'
      }`}
    >
      {bullish ? 'Bull' : 'Bear'}
    </span>
  )
}

function ResultChip({ call, horizon }: { call: TraderCall; horizon: TraderCallHorizon }) {
  const result: TraderCallResult | undefined = call.results.find((r) => r.horizon_days === horizon)
  const base = 'rounded-md px-1.5 py-0.5 text-[10px] font-semibold tabular-nums'
  if (!result) {
    return (
      <span className={`${base} bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400`}>
        {horizon}d pending
      </span>
    )
  }
  if (result.excluded) {
    return (
      <span
        className={`${base} bg-zinc-100 text-zinc-400 line-through dark:bg-zinc-800 dark:text-zinc-500`}
        title="Not scored: the later price didn't match the asset priced at call time"
      >
        {horizon}d n/a
      </span>
    )
  }
  const value = signedReturn(call.direction, result.return_pct)
  return (
    <span
      className={`${base} ${
        result.correct
          ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400'
          : 'bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400'
      }`}
      title={`Price ${formatPrice(result.price_at_horizon)} after ${horizon}d`}
    >
      {horizon}d {formatReturnPct(value)}
    </span>
  )
}

function TickerButton({ ticker, onClick }: { ticker: string; onClick?: (ticker: string) => void }) {
  if (!onClick) return <span className="font-semibold">${ticker}</span>
  return (
    <button
      type="button"
      onClick={() => onClick(ticker)}
      className="font-semibold text-sky-700 hover:underline dark:text-sky-400"
    >
      ${ticker}
    </button>
  )
}

function TickerBreakdown({
  tickers,
  horizon,
  onTickerClick,
}: {
  tickers: TraderTickerStat[]
  horizon: TraderCallHorizon
  onTickerClick?: (ticker: string) => void
}) {
  if (tickers.length === 0) {
    return <p className="text-sm text-zinc-500">No tickers called yet.</p>
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-200 dark:border-zinc-800">
      <table className="w-full min-w-[420px] text-left text-sm">
        <thead className="bg-zinc-50 text-[10px] font-semibold uppercase tracking-wider text-zinc-500 dark:bg-zinc-900/70">
          <tr>
            <th className="px-3 py-2">Ticker</th>
            <th className="px-3 py-2 text-right">Calls</th>
            <th className="px-3 py-2">Bull / Bear</th>
            <th className="px-3 py-2 text-right">Hit rate ({horizon}d)</th>
            <th className="px-3 py-2 text-right">Avg return</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
          {tickers.map((t) => {
            const bullShare = t.calls ? (t.bullish_calls / t.calls) * 100 : 0
            return (
              <tr key={t.ticker} className="bg-white dark:bg-zinc-900/40">
                <td className="px-3 py-2">
                  <TickerButton ticker={t.ticker} onClick={onTickerClick} />
                  {t.asset_kind && (
                    <span className="ml-1.5 text-[10px] uppercase text-zinc-400">{t.asset_kind}</span>
                  )}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-zinc-600 dark:text-zinc-300">{t.calls}</td>
                <td className="px-3 py-2">
                  <div
                    className="flex h-1.5 w-24 overflow-hidden rounded-full bg-rose-400/80"
                    title={`${t.bullish_calls} bullish, ${t.bearish_calls} bearish`}
                  >
                    <div className="bg-emerald-500" style={{ width: `${bullShare}%` }} />
                  </div>
                  <span className="text-[10px] tabular-nums text-zinc-500">
                    {t.bullish_calls} / {t.bearish_calls}
                  </span>
                </td>
                <td
                  className={`px-3 py-2 text-right font-semibold tabular-nums ${
                    t.hit_rate == null ? 'text-zinc-400' : hitRateClass(t.hit_rate)
                  }`}
                >
                  {t.hit_rate == null ? '—' : `${Math.round(t.hit_rate * 100)}%`}
                  <span className="ml-1 text-[10px] font-normal text-zinc-400">
                    ({t.correct_calls}/{t.graded_calls})
                  </span>
                </td>
                <td className={`px-3 py-2 text-right font-semibold tabular-nums ${returnClass(t.avg_return_pct)}`}>
                  {formatReturnPct(t.avg_return_pct)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function CallOutcomeChart({ points, horizon }: { points: ChartPoint[]; horizon: TraderCallHorizon }) {
  if (points.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-zinc-200 p-6 text-center text-sm text-zinc-500 dark:border-zinc-800">
        No calls graded at {horizon}d yet.
      </p>
    )
  }
  const wins = points.filter((p) => p.correct)
  const losses = points.filter((p) => !p.correct)
  return (
    <div className="h-56 w-full" role="img" aria-label={`Return of each call ${horizon} days later`}>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-zinc-200 dark:text-zinc-800" />
          <XAxis
            type="number"
            dataKey="t"
            domain={['dataMin', 'dataMax']}
            scale="time"
            tickFormatter={(t: number) => new Date(t).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
            tick={{ fontSize: 10, fill: '#71717a' }}
            stroke="#a1a1aa"
          />
          <YAxis
            type="number"
            dataKey="ret"
            tickFormatter={(v: number) => `${v > 0 ? '+' : ''}${v.toFixed(0)}%`}
            tick={{ fontSize: 10, fill: '#71717a' }}
            stroke="#a1a1aa"
            width={48}
          />
          <ReferenceLine y={0} stroke="#a1a1aa" />
          <Tooltip
            cursor={{ strokeDasharray: '3 3' }}
            content={({ active, payload }) => {
              const p = active && payload?.[0]?.payload ? (payload[0].payload as ChartPoint) : null
              if (!p) return null
              return (
                <div className="rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5 text-xs shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
                  <div className="font-semibold text-zinc-800 dark:text-zinc-100">
                    ${p.ticker} · {p.direction}
                  </div>
                  <div className="text-zinc-500">{new Date(p.t).toLocaleString()}</div>
                  <div className={returnClass(p.ret)}>
                    {formatReturnPct(p.ret)} after {horizon}d
                  </div>
                </div>
              )
            }}
          />
          <Scatter name="Correct" data={wins} fill={WIN_COLOR} isAnimationActive={false} />
          <Scatter name="Wrong" data={losses} fill={LOSS_COLOR} isAnimationActive={false} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

function CallRow({
  call,
  onTickerClick,
}: {
  call: TraderCall
  onTickerClick?: (ticker: string) => void
}) {
  return (
    <li className="space-y-1.5 px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <TickerButton ticker={call.ticker} onClick={onTickerClick} />
        <DirectionPill direction={call.direction} />
        <span className="tabular-nums text-zinc-500">@ {formatPrice(call.price_at_call)}</span>
        <span className="text-[11px] text-zinc-400">{formatDateTime(call.called_at)}</span>
        <span className="ml-auto flex flex-wrap gap-1">
          {([1, 7, 30] as TraderCallHorizon[]).map((h) => (
            <ResultChip key={h} call={call} horizon={h} />
          ))}
        </span>
      </div>
      {call.tweet_text && (
        <p className="line-clamp-2 text-xs text-zinc-600 dark:text-zinc-400">
          {call.tweet_url ? (
            <a href={call.tweet_url} target="_blank" rel="noreferrer" className="hover:underline">
              {call.tweet_text}
            </a>
          ) : (
            call.tweet_text
          )}
        </p>
      )}
    </li>
  )
}

export default function TraderDetailPanel({ screenName, horizon, onClose, onTickerClick }: Props) {
  const { data, loading, error } = useTraderDetail(screenName, horizon)

  const points = useMemo<ChartPoint[]>(() => {
    if (!data) return []
    const out: ChartPoint[] = []
    for (const call of data.recent_calls) {
      const result = call.results.find((r) => r.horizon_days === horizon)
      const at = parseUtc(call.called_at)
      if (!result || result.excluded || !at) continue
      out.push({
        t: at.getTime(),
        ret: signedReturn(call.direction, result.return_pct),
        ticker: call.ticker,
        direction: call.direction,
        correct: result.correct,
      })
    }
    return out
  }, [data, horizon])

  const summary = data?.summary

  return (
    <section
      aria-label={`Calls by @${screenName}`}
      className="space-y-4 rounded-2xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950"
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-base font-bold text-zinc-900 dark:text-zinc-100">
            <a
              href={`https://x.com/${encodeURIComponent(screenName)}`}
              target="_blank"
              rel="noreferrer"
              className="hover:underline"
            >
              @{screenName}
            </a>
          </h3>
          {summary && summary.total_calls > 0 && (
            <p className="text-[11px] text-zinc-500">
              {summary.total_calls} calls on {summary.distinct_tickers} tickers ·{' '}
              <span className="text-emerald-600 dark:text-emerald-400">{summary.bullish_calls} bullish</span> /{' '}
              <span className="text-rose-600 dark:text-rose-400">{summary.bearish_calls} bearish</span> · since{' '}
              {formatDate(summary.first_called_at)}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg px-2 py-1 text-xs font-semibold text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800 dark:hover:bg-zinc-900 dark:hover:text-zinc-200"
        >
          Close ✕
        </button>
      </header>

      {loading && !data ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-16 animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-900" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load this trader's calls.</p>
      ) : !data || data.recent_calls.length === 0 ? (
        <p className="text-sm text-zinc-500">No calls recorded for @{screenName} yet.</p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2">
            {data.horizons.map((h) => (
              <div
                key={h.horizon_days}
                className={`rounded-xl border p-2.5 ${
                  h.horizon_days === horizon
                    ? 'border-zinc-400 dark:border-zinc-600'
                    : 'border-zinc-200 dark:border-zinc-800'
                }`}
              >
                <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                  {h.horizon_days}d
                </div>
                <div
                  className={`text-lg font-bold tabular-nums ${
                    h.hit_rate == null ? 'text-zinc-400' : hitRateClass(h.hit_rate)
                  }`}
                >
                  {h.hit_rate == null ? '—' : `${Math.round(h.hit_rate * 100)}%`}
                </div>
                <div className="flex justify-between text-[10px] tabular-nums text-zinc-500">
                  <span>{h.graded_calls} graded</span>
                  <span className={returnClass(h.avg_return_pct)}>{formatReturnPct(h.avg_return_pct)}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="space-y-1.5">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
              Call outcomes after {horizon}d
            </h4>
            <CallOutcomeChart points={points} horizon={horizon} />
            {points.length > 0 && (
              <p className="text-[10px] text-zinc-400">
                Each dot is one of the {data.recent_calls.length} most recent calls, signed for direction:{' '}
                <span className="text-emerald-600 dark:text-emerald-400">green</span> worked out,{' '}
                <span className="text-rose-600 dark:text-rose-400">red</span> didn't.
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Mentioned tickers</h4>
            <TickerBreakdown tickers={data.tickers} horizon={horizon} onTickerClick={onTickerClick} />
          </div>

          <div className="space-y-1.5">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Recent calls</h4>
            <ul className="divide-y divide-zinc-100 rounded-xl border border-zinc-200 dark:divide-zinc-900 dark:border-zinc-800">
              {data.recent_calls.map((call) => (
                <CallRow key={call.id} call={call} onTickerClick={onTickerClick} />
              ))}
            </ul>
          </div>
        </>
      )}
    </section>
  )
}
