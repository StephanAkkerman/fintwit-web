import type { ReactNode } from 'react'
import type { ActivitySummary, ActivityTickerSummary, AssetKind } from '../types'
import { useActivitySummary } from '../hooks/useActivitySummary'

interface Props {
  assetKind: AssetKind
  windowHours?: number
  userFilter?: string | null
  subscriberOnly?: boolean
  onTickerClick?: (ticker: string) => void
}

function windowLabel(h: number): string {
  return h < 48 ? `${h}h` : `${h / 24}d`
}

function toneClass(delta: number): string {
  if (delta > 0) return 'text-emerald-400'
  if (delta < 0) return 'text-rose-400'
  return 'text-zinc-500'
}

function Delta({ delta, text }: { delta: number; text: string }) {
  const arrow = delta > 0 ? '▲' : delta < 0 ? '▼' : '·'
  return (
    <span className={`font-mono text-[11px] font-semibold tabular-nums ${toneClass(delta)}`}>
      {arrow} {text}
    </span>
  )
}

/** Count delta vs the previous window, as a % when the baseline allows it. */
function CountDelta({ current, previous, asPct }: { current: number; previous: number; asPct: boolean }) {
  const diff = current - previous
  if (asPct) {
    if (previous === 0) {
      return current === 0 ? <Delta delta={0} text="flat" /> : <span className="font-mono text-[11px] text-zinc-500">new</span>
    }
    const pct = (diff / previous) * 100
    return <Delta delta={diff} text={`${Math.abs(pct).toFixed(0)}%`} />
  }
  return <Delta delta={diff} text={String(Math.abs(diff))} />
}

function Tile({ label, children, sub }: { label: string; children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-xl border border-zinc-800 bg-zinc-950/40 px-3 py-2.5">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">{label}</span>
      <div className="flex min-w-0 items-baseline gap-2">{children}</div>
      {sub && <div className="truncate text-[10px] font-mono text-zinc-500">{sub}</div>}
    </div>
  )
}

function TickerValue({ item, onTickerClick }: { item: ActivityTickerSummary; onTickerClick?: (ticker: string) => void }) {
  const cls = 'truncate font-mono text-lg font-bold text-zinc-100'
  if (!onTickerClick) return <span className={cls}>{item.ticker}</span>
  return (
    <button type="button" onClick={() => onTickerClick(item.ticker)} className={`${cls} hover:text-sky-300 hover:underline`}>
      {item.ticker}
    </button>
  )
}

function formatPct(v: number): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(Math.abs(v) >= 10 ? 1 : 2)}%`
}

function Tiles({ data, onTickerClick }: { data: ActivitySummary; onTickerClick?: (ticker: string) => void }) {
  const { tweets, authors, sentiment, top_ticker, top_mover } = data
  const bullPct = sentiment.bull_pct
  const prevBullPct = sentiment.prev_bull_pct
  const bullish = bullPct === null ? null : bullPct >= 50

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
      <Tile label="Tweets" sub={`${tweets.previous} previous`}>
        <span className="font-mono text-lg font-bold tabular-nums text-zinc-100">{tweets.current}</span>
        <CountDelta current={tweets.current} previous={tweets.previous} asPct />
      </Tile>

      <Tile label="Accounts" sub={`${authors.previous} previous`}>
        <span className="font-mono text-lg font-bold tabular-nums text-zinc-100">{authors.current}</span>
        <CountDelta current={authors.current} previous={authors.previous} asPct={false} />
      </Tile>

      <Tile label="Net sentiment" sub={`${sentiment.bull} bull · ${sentiment.bear} bear`}>
        {bullPct === null ? (
          <span className="font-mono text-lg font-bold text-zinc-500">—</span>
        ) : (
          <>
            <span className={`font-mono text-lg font-bold tabular-nums ${bullish ? 'text-emerald-400' : 'text-rose-400'}`}>
              {bullish ? `${bullPct.toFixed(0)}% bull` : `${(100 - bullPct).toFixed(0)}% bear`}
            </span>
            {prevBullPct !== null && (
              <Delta delta={Math.round(bullPct - prevBullPct)} text={`${Math.abs(Math.round(bullPct - prevBullPct))}pt`} />
            )}
          </>
        )}
      </Tile>

      <Tile
        label="Most talked"
        sub={top_ticker ? `${top_ticker.unique_authors} accounts · ${top_ticker.sentiment_label.toLowerCase()}` : undefined}
      >
        {top_ticker ? (
          <>
            <TickerValue item={top_ticker} onTickerClick={onTickerClick} />
            <span className="font-mono text-[11px] text-zinc-400">{top_ticker.mentions}×</span>
          </>
        ) : (
          <span className="font-mono text-lg font-bold text-zinc-500">—</span>
        )}
      </Tile>

      <Tile label="Biggest mover" sub={top_mover ? `${top_mover.mentions} mentions` : undefined}>
        {top_mover && top_mover.price_direction !== null ? (
          <>
            <TickerValue item={top_mover} onTickerClick={onTickerClick} />
            <span className={`font-mono text-[11px] font-semibold tabular-nums ${toneClass(top_mover.price_direction)}`}>
              {formatPct(top_mover.price_direction)}
            </span>
          </>
        ) : (
          <span className="font-mono text-lg font-bold text-zinc-500">—</span>
        )}
      </Tile>
    </div>
  )
}

export function ActivityPulseWidget({ assetKind, windowHours = 24, userFilter = null, subscriberOnly = false, onTickerClick }: Props) {
  const { data, loading, error } = useActivitySummary(assetKind, windowHours, userFilter, subscriberOnly)

  let body: ReactNode
  if (loading && !data) {
    body = (
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {[0, 1, 2, 3, 4].map(i => (
          <div key={i} className="h-[68px] rounded-xl bg-zinc-800 animate-pulse" />
        ))}
      </div>
    )
  } else if (error || !data) {
    body = <p className="text-sm text-zinc-500">Failed to load activity summary.</p>
  } else if (data.tweets.current === 0 && data.tweets.previous === 0) {
    body = <p className="text-sm text-zinc-500">No tweets in this window yet.</p>
  } else {
    body = <Tiles data={data} onTickerClick={onTickerClick} />
  }

  return (
    <section aria-label="Activity pulse" className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-[13px] font-semibold text-zinc-100">Activity Pulse</h2>
        <span className="text-[10px] text-zinc-500 font-mono">last {windowLabel(windowHours)} vs previous {windowLabel(windowHours)}</span>
      </div>
      {body}
    </section>
  )
}
