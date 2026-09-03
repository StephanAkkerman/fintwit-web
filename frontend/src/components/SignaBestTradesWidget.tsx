import { useMemo, useState } from 'react'
import { useSignaBestTrades } from '../hooks/useSignaBestTrades'
import type { SignaBestTrade } from '../types'
import { directionTextClass } from '../utils/directionColor'
import { absoluteTime, directionArrow, gradeClasses, relativeTime } from '../utils/signaFormat'

const TIMEFRAME_LABEL = 'Daily (1D) · 20–60 trading days'
const SOURCE_LABEL = 'Signa Signal Engine · scored_signals'

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-zinc-50 px-2.5 py-2 dark:bg-zinc-900/70">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">{label}</div>
      <div className="mt-0.5 text-sm font-bold tabular-nums text-zinc-800 dark:text-zinc-100">{value}</div>
    </div>
  )
}

function TradeCard({ trade, rank }: { trade: SignaBestTrade; rank: number }) {
  const [open, setOpen] = useState(false)
  const colorClass = directionTextClass(trade.direction)
  const arrow = directionArrow(trade.direction)
  const drivers = trade.key_drivers ?? []
  const confidencePct =
    typeof trade.confidence === 'number' ? `${Math.round(trade.confidence * 100)}%` : '—'

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-start gap-3 text-left"
      >
        <span className="mt-0.5 shrink-0 text-sm font-bold tabular-nums text-zinc-400">#{rank}</span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-base font-bold tracking-tight">{trade.symbol}</span>
            <span className={`text-xs font-bold ${colorClass}`}>
              {arrow} {(trade.direction ?? 'NEUTRAL').toUpperCase()}
            </span>
            {trade.grade && (
              <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold ${gradeClasses(trade.grade)}`}>
                {trade.grade.toUpperCase()}
              </span>
            )}
            <span className="ml-auto text-sm font-bold tabular-nums text-zinc-700 dark:text-zinc-200">
              {trade.composite_score != null ? Math.round(trade.composite_score) : '—'}
            </span>
          </div>

          {trade.reason && (
            <p className={`mt-1 text-xs text-zinc-500 dark:text-zinc-400 ${open ? '' : 'line-clamp-1'}`}>
              {trade.reason}
            </p>
          )}

          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {typeof trade.alert_tier === 'number' && (
              <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                Tier {trade.alert_tier}
              </span>
            )}
            {(trade.categories ?? []).map((cat) => (
              <span
                key={cat}
                className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
              >
                {cat}
              </span>
            ))}
          </div>
        </div>
      </button>

      {open && (
        <div className="mt-3 border-t border-zinc-100 pt-3 dark:border-zinc-900">
          <div className="text-[11px] text-zinc-500 dark:text-zinc-400">
            {trade.generated_at && (
              <>
                Last updated {relativeTime(trade.generated_at)} ({absoluteTime(trade.generated_at)})
                <span className="mx-1.5">·</span>
              </>
            )}
            Source {SOURCE_LABEL}
            <span className="mx-1.5">·</span>
            Timeframe {TIMEFRAME_LABEL}
          </div>

          <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-5">
            <Metric label="Score" value={trade.composite_score != null ? String(Math.round(trade.composite_score)) : '—'} />
            <Metric label="Grade" value={(trade.grade ?? '—').toUpperCase()} />
            <Metric label="Confidence" value={confidencePct} />
            <Metric label="Models" value={trade.model_count != null ? String(trade.model_count) : '—'} />
            <Metric label="Regime" value={trade.regime ?? '—'} />
          </div>

          {drivers.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {drivers.map((driver, i) => (
                <span
                  key={`${driver}-${i}`}
                  className="rounded-md bg-zinc-100 px-2 py-1 text-[11px] text-zinc-600 dark:bg-zinc-800/80 dark:text-zinc-300"
                >
                  {driver}
                </span>
              ))}
            </div>
          )}

          {trade.website && (
            <a
              href={trade.website}
              target="_blank"
              rel="noreferrer"
              className="mt-3 inline-block text-[11px] font-semibold text-sky-600 hover:underline dark:text-sky-400"
            >
              Open in Signa →
            </a>
          )}
        </div>
      )}
    </div>
  )
}

export default function SignaBestTradesWidget() {
  const { data, loading, error } = useSignaBestTrades(100)

  // Order by composite score, then model confidence (strength proxy), then tier.
  const ranked = useMemo(() => {
    return [...data].sort((a, b) => {
      const score = (b.composite_score ?? 0) - (a.composite_score ?? 0)
      if (score !== 0) return score
      const conf = (b.confidence ?? 0) - (a.confidence ?? 0)
      if (conf !== 0) return conf
      return (b.alert_tier ?? 0) - (a.alert_tier ?? 0)
    })
  }, [data])

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Signa · Best Trades</h2>
          <p className="text-[10px] font-mono text-zinc-500">
            ranked by composite score · getsigna.ai signal engine
          </p>
        </div>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          {loading ? '…' : `${ranked.length} signals`}
        </span>
      </div>

      <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-400">
        <span>Tier 3 alerts are not displayed here.</span>
        <a
          href="https://app.getsigna.ai/dashboard/best-trades"
          target="_blank"
          rel="noreferrer"
          className="ml-auto shrink-0 font-semibold hover:underline"
        >
          View on Signa →
        </a>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-900" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load Signa best trades.</p>
      ) : ranked.length === 0 ? (
        <p className="text-sm text-zinc-500">No Signa signals available right now.</p>
      ) : (
        <div className="space-y-2">
          {ranked.map((trade, idx) => (
            <TradeCard key={trade.symbol + idx} trade={trade} rank={idx + 1} />
          ))}
        </div>
      )}
    </div>
  )
}
