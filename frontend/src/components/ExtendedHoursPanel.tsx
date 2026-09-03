import { useState } from 'react'
import type {
  ExtendedHoursEtf,
  ExtendedHoursFuture,
  ExtendedHoursSnapshot,
  ExtendedHoursTweetStats,
} from '../types'
import { useExtendedHours } from '../hooks/useExtendedHours'

function fmtPct(n: number): string {
  const sign = n >= 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

function fmtWindowTime(isoStart: string, isoEnd: string): string {
  const opts: Intl.DateTimeFormatOptions = {
    hour: 'numeric',
    minute: '2-digit',
    timeZone: 'America/New_York',
    hour12: true,
  }
  const start = new Date(isoStart).toLocaleTimeString('en-US', opts)
  const end   = new Date(isoEnd).toLocaleTimeString('en-US', opts)
  return `${start} – ${end} ET`
}

function sessionBadgeClass(session: string): string {
  if (session === 'pre-market')
    return 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
  if (session === 'after-hours')
    return 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300'
  return 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
}

function sessionLabel(session: string): string {
  if (session === 'pre-market') return 'Pre-market'
  if (session === 'after-hours') return 'After-hours'
  return session
}

function FutureCard({ f }: { f: ExtendedHoursFuture }) {
  const positive = f.change_pct >= 0
  return (
    <div className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
      <p className="text-xs font-semibold text-zinc-500 dark:text-zinc-400">{f.label}</p>
      <p className="mt-0.5 text-sm font-bold text-zinc-900 dark:text-zinc-100">
        {f.price.toLocaleString()}
      </p>
      <p className={`text-[11px] font-semibold ${positive ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
        {fmtPct(f.change_pct)}
      </p>
    </div>
  )
}

function EtfCard({ e }: { e: ExtendedHoursEtf }) {
  const hasExt = e.extended_price !== null && e.extended_change_pct !== null
  const extPositive = (e.extended_change_pct ?? 0) >= 0
  return (
    <div className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
      <p className="text-xs font-semibold text-zinc-500 dark:text-zinc-400">{e.symbol}</p>
      <p className="mt-0.5 text-sm font-bold text-zinc-900 dark:text-zinc-100">
        ${e.price.toFixed(2)}
      </p>
      {hasExt && (
        <p className={`text-[11px] font-semibold ${extPositive ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
          {e.extended_price!.toFixed(2)} · {fmtPct(e.extended_change_pct!)}
        </p>
      )}
    </div>
  )
}

function SentimentBar({ dist }: { dist: ExtendedHoursTweetStats['sentiment_distribution'] }) {
  const total = dist.BULL + dist.BEAR + dist.NEUTRAL
  if (total === 0) return null
  const bullPct    = (dist.BULL    / total) * 100
  const bearPct    = (dist.BEAR    / total) * 100
  const neutralPct = 100 - bullPct - bearPct
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full">
      <div style={{ width: `${bullPct}%` }}    className="bg-emerald-500" />
      <div style={{ width: `${neutralPct}%` }} className="bg-zinc-500" />
      <div style={{ width: `${bearPct}%` }}    className="bg-red-500" />
    </div>
  )
}

function sentimentDot(sentiment: string): string {
  if (sentiment === 'BULL') return 'bg-emerald-500'
  if (sentiment === 'BEAR') return 'bg-red-500'
  return 'bg-zinc-500'
}

function PanelBody({ snapshot }: { snapshot: ExtendedHoursSnapshot }) {
  const { session, window_start, window_end, futures, etfs, tweet_stats } = snapshot
  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${sessionBadgeClass(session)}`}>
          {sessionLabel(session)}
        </span>
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          {fmtWindowTime(window_start, window_end)}
        </span>
        <span className="ml-auto rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          Live
        </span>
      </div>

      {/* Futures */}
      {futures.length > 0 && (
        <div>
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">Futures</p>
          <div className="grid grid-cols-3 gap-2">
            {futures.map((f) => <FutureCard key={f.label} f={f} />)}
          </div>
        </div>
      )}

      {/* ETFs */}
      {etfs.length > 0 && (
        <div>
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">ETFs (extended)</p>
          <div className="grid grid-cols-3 gap-2">
            {etfs.map((e) => <EtfCard key={e.symbol} e={e} />)}
          </div>
        </div>
      )}

      {/* Tweet stats */}
      <div>
        <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
          {tweet_stats.total_mentions} mentions · {sessionLabel(session)} window
        </p>
        <div className="flex flex-wrap items-center gap-1.5">
          {tweet_stats.top_tickers.slice(0, 5).map((t) => (
            <span
              key={t.ticker}
              className="flex items-center gap-1 rounded-full border border-zinc-200 bg-zinc-50 px-2 py-0.5 text-[11px] font-semibold text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
            >
              <span className={`inline-block h-1.5 w-1.5 rounded-full ${sentimentDot(t.sentiment)}`} />
              {t.ticker}
              <span className="text-zinc-400">{t.mentions}</span>
            </span>
          ))}
        </div>
        <div className="mt-2">
          <SentimentBar dist={tweet_stats.sentiment_distribution} />
          <div className="mt-1 flex justify-between text-[10px] text-zinc-400">
            <span>Bull {tweet_stats.sentiment_distribution.BULL}</span>
            <span>Bear {tweet_stats.sentiment_distribution.BEAR}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function ExtendedHoursPanel() {
  const { data, loading } = useExtendedHours()
  const [expanded, setExpanded] = useState(false)

  if (loading || !data) return null
  if (data.session === 'regular') return null

  if (data.session === 'closed' && !expanded) {
    return (
      <div className="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950">
        <button
          type="button"
          aria-label="Expand last session recap"
          onClick={() => setExpanded(true)}
          className="flex w-full items-center justify-between text-sm text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
        >
          <span>Market closed · last session recap</span>
          <span className="text-xs">▼</span>
        </button>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      {data.session === 'closed' && (
        <div className="mb-3 flex items-center justify-between">
          <span className="text-xs text-zinc-400">Last session recap</span>
          <button
            type="button"
            onClick={() => setExpanded(false)}
            className="text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
          >
            ▲
          </button>
        </div>
      )}
      <PanelBody snapshot={data} />
    </div>
  )
}
