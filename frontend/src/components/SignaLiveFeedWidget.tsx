import { useMemo, useState } from 'react'
import { SIGNA_LIVE_FEED_REFRESH_MS, useSignaLiveFeed } from '../hooks/useSignaLiveFeed'
import type { SignaLiveSignal } from '../types'
import { directionTextClass } from '../utils/directionColor'
import { absoluteTime, directionArrow, gradeClasses, relativeTime } from '../utils/signaFormat'

const REFRESH_MINUTES = Math.round(SIGNA_LIVE_FEED_REFRESH_MS / 60000)

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-zinc-50 px-2.5 py-2 dark:bg-zinc-900/70">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">{label}</div>
      <div className="mt-0.5 text-sm font-bold tabular-nums text-zinc-800 dark:text-zinc-100">{value}</div>
    </div>
  )
}

function price(value: number | null | undefined): string {
  return typeof value === 'number' ? `$${value.toFixed(2)}` : '—'
}

function FeedCard({ signal, rank }: { signal: SignaLiveSignal; rank: number }) {
  const [open, setOpen] = useState(false)
  const colorClass = directionTextClass(signal.direction ?? signal.signal)
  const arrow = directionArrow(signal.direction ?? signal.signal)
  const confidencePct =
    typeof signal.confidence === 'number' ? `${Math.round(signal.confidence * 100)}%` : '—'
  const sizePct =
    typeof signal.position_size_pct === 'number'
      ? `${(signal.position_size_pct * 100).toFixed(1)}%`
      : '—'

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-start gap-3 text-left"
      >
        <span className="mt-0.5 shrink-0 text-sm font-bold tabular-nums text-zinc-400">#{rank}</span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-base font-bold tracking-tight">{signal.symbol}</span>
            <span className={`text-xs font-bold ${colorClass}`}>
              {arrow} {(signal.signal ?? signal.direction ?? 'NEUTRAL').toUpperCase()}
            </span>
            {signal.grade && (
              <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold ${gradeClasses(signal.grade)}`}>
                {signal.grade.toUpperCase()}
              </span>
            )}
            {signal.created_at && (
              <span className="text-[11px] text-zinc-400">{relativeTime(signal.created_at)}</span>
            )}
            <span className="ml-auto text-sm font-bold tabular-nums text-zinc-700 dark:text-zinc-200">
              {signal.score != null ? Math.round(signal.score) : '—'}
            </span>
          </div>

          {signal.reason && (
            <p className={`mt-1 text-xs text-zinc-500 dark:text-zinc-400 ${open ? '' : 'line-clamp-1'}`}>
              {signal.reason}
            </p>
          )}

          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {signal.model_name && (
              <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                {signal.model_name}
              </span>
            )}
            {signal.category && (
              <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                {signal.category}
              </span>
            )}
            {typeof signal.tier === 'number' && (
              <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                Tier {signal.tier}
              </span>
            )}
            {signal.conflict_detected && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
                Conflict
              </span>
            )}
          </div>
        </div>
      </button>

      {open && (
        <div className="mt-3 border-t border-zinc-100 pt-3 dark:border-zinc-900">
          <div className="text-[11px] text-zinc-500 dark:text-zinc-400">
            {signal.created_at && (
              <>
                Signalled {relativeTime(signal.created_at)} ({absoluteTime(signal.created_at)})
                <span className="mx-1.5">·</span>
              </>
            )}
            Raw model signal — compare with daily consensus on Best Trades
          </div>

          {signal.model_source && (
            <p className="mt-2 text-[11px] italic text-zinc-500 dark:text-zinc-400">{signal.model_source}</p>
          )}

          <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-5">
            <Metric label="Entry" value={price(signal.entry_price)} />
            <Metric label="Stop" value={price(signal.stop_level)} />
            <Metric label="Target" value={price(signal.target_price)} />
            <Metric label="Confidence" value={confidencePct} />
            <Metric label="Size" value={sizePct} />
          </div>

          {signal.website && (
            <a
              href={signal.website}
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

export default function SignaLiveFeedWidget() {
  const { data, loading, error, lastUpdated } = useSignaLiveFeed()

  // Same ordering as Best Trades: composite/raw score, then confidence, then
  // tier — with the freshest signal winning ties (some entries lack a score).
  const ranked = useMemo(() => {
    return [...data].sort((a, b) => {
      const score = (b.score ?? 0) - (a.score ?? 0)
      if (score !== 0) return score
      const conf = (b.confidence ?? 0) - (a.confidence ?? 0)
      if (conf !== 0) return conf
      const tier = (b.tier ?? 0) - (a.tier ?? 0)
      if (tier !== 0) return tier
      const at = new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime()
      return Number.isNaN(at) ? 0 : at
    })
  }, [data])

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Signa · Live Feed</h2>
          <p className="text-[10px] font-mono text-zinc-500">
            directional model signals · auto-refresh {REFRESH_MINUTES}m
            {lastUpdated ? ` · updated ${relativeTime(new Date(lastUpdated).toISOString())}` : ''}
          </p>
        </div>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          {loading ? '…' : `${ranked.length} signals`}
        </span>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-900" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load Signa live feed.</p>
      ) : ranked.length === 0 ? (
        <p className="text-sm text-zinc-500">No directional Signa signals right now.</p>
      ) : (
        <div className="space-y-2">
          {ranked.map((signal, idx) => (
            <FeedCard key={(signal.id ?? signal.symbol) + idx} signal={signal} rank={idx + 1} />
          ))}
        </div>
      )}
    </div>
  )
}
