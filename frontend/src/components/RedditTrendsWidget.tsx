import { MessagesSquare } from 'lucide-react'
import type { RedditTickerTrend } from '../types'
import { useRedditTrends } from '../hooks/useRedditTrends'
import type { PortfolioTickerLookup } from '../hooks/usePortfolioTickers'
import { PortfolioTickerBadge } from './PortfolioTickerBadge'

interface Props {
  limit?: number
  portfolioLookup?: PortfolioTickerLookup
  onTickerSelect?: (ticker: string) => void
}

function sentimentTone(sentiment: string | null | undefined): string {
  if (sentiment === 'bullish') return 'text-emerald-400'
  if (sentiment === 'bearish') return 'text-rose-400'
  return 'text-zinc-400'
}

// Momentum is (now - prev) / (prev + 1). Anything past +0.5 is a ticker
// getting meaningfully louder, which is the signal the ranking exists for.
function momentumTone(momentum: number): { color: string; arrow: string } {
  if (momentum >= 0.5) return { color: 'text-emerald-400', arrow: '▲' }
  if (momentum <= -0.3) return { color: 'text-rose-400', arrow: '▼' }
  return { color: 'text-zinc-400', arrow: '·' }
}

function formatSigned(value: number): string {
  return (value >= 0 ? '+' : '') + value.toFixed(2)
}

function formatAgo(iso: string | null): string {
  if (!iso) return 'never'
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000))
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

function Row({
  item,
  maxMentions,
  portfolioStatus,
  onTickerSelect,
}: {
  item: RedditTickerTrend
  maxMentions: number
  portfolioStatus: ReturnType<PortfolioTickerLookup>
  onTickerSelect?: (ticker: string) => void
}) {
  const { color, arrow } = momentumTone(item.momentum)
  // Bar length is share of the loudest ticker, so the column reads as a
  // ranking at a glance rather than as absolute counts nobody can calibrate.
  const share = maxMentions > 0 ? Math.max(4, (item.mentions / maxMentions) * 100) : 0

  return (
    <div
      className="grid items-center gap-2 border-b border-zinc-900 py-1.5 last:border-b-0"
      style={{ gridTemplateColumns: '72px 1fr 64px 56px' }}
    >
      <span className="flex items-center gap-1 font-mono text-[11px] font-semibold text-zinc-100">
        {onTickerSelect ? (
          <button
            type="button"
            onClick={() => onTickerSelect(item.symbol)}
            className="hover:underline"
          >
            {item.symbol}
          </button>
        ) : (
          item.symbol
        )}
        {item.is_emerging && (
          <span
            title="No mentions in the previous window"
            className="rounded bg-amber-500/15 px-1 text-[9px] font-bold text-amber-400"
          >
            NEW
          </span>
        )}
        <PortfolioTickerBadge status={portfolioStatus} />
      </span>

      <span className="flex items-center gap-2">
        <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-800">
          <span
            className="block h-full rounded-full bg-zinc-500"
            style={{ width: `${share}%` }}
          />
        </span>
        <span className="w-14 shrink-0 text-right font-mono text-[10px] tabular-nums text-zinc-500">
          {item.mentions}
          <span className="text-zinc-600">/{item.previous_mentions}</span>
        </span>
      </span>

      <span
        className={`text-right font-mono text-[10px] tabular-nums ${sentimentTone(item.sentiment)}`}
      >
        {formatSigned(item.sentiment_score)}
      </span>

      <span className={`text-right font-mono text-[11px] font-bold tabular-nums ${color}`}>
        {arrow} {formatSigned(item.momentum)}
      </span>
    </div>
  )
}

export function RedditTrendsWidget({ limit = 10, portfolioLookup, onTickerSelect }: Props) {
  const { data, loading, error } = useRedditTrends(limit)

  if (loading) {
    return (
      <div className="flex flex-col gap-3 rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
        <div className="h-4 w-32 animate-pulse rounded bg-zinc-800" />
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-5 animate-pulse rounded bg-zinc-800" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-500">
        Failed to load Reddit trends.
      </div>
    )
  }

  // Three distinct empty states, because the fix for each is different:
  // install the package, wait for the first run, or nothing is being discussed.
  if (!data.available) {
    return (
      <div className="flex items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-500">
        <MessagesSquare className="h-4 w-4 shrink-0" aria-hidden="true" />
        Reddit trend analysis is not enabled in this deployment.
      </div>
    )
  }

  if (!data.captured_at) {
    return (
      <div className="flex items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-500">
        <MessagesSquare className="h-4 w-4 shrink-0" aria-hidden="true" />
        Waiting for the first Reddit scrape.
      </div>
    )
  }

  if (data.tickers.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-500">
        <MessagesSquare className="h-4 w-4 shrink-0" aria-hidden="true" />
        No tickers recognised in the latest scrape.
      </div>
    )
  }

  const maxMentions = Math.max(...data.tickers.map((t) => t.mentions), 0)

  return (
    <div className="flex flex-col gap-0 rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-[13px] font-semibold text-zinc-100">Reddit Trends</h2>
        <span className="font-mono text-[10px] text-zinc-500">
          {data.subreddits.length} subs · {formatAgo(data.captured_at)}
        </span>
      </div>
      <div className="mb-2 flex items-center gap-2 font-mono text-[10px] text-zinc-600">
        <span className="w-[72px]">ticker</span>
        <span className="flex-1">mentions now/prev</span>
        <span className="w-16 text-right">sent</span>
        <span className="w-14 text-right">mom</span>
      </div>
      <div className="flex flex-col">
        {data.tickers.map((item) => (
          <Row
            key={item.symbol}
            item={item}
            maxMentions={maxMentions}
            portfolioStatus={portfolioLookup?.(item.symbol) ?? null}
            onTickerSelect={onTickerSelect}
          />
        ))}
      </div>
      {(data.emerging?.length || data.fading?.length) && (
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 border-t border-zinc-900 pt-2 font-mono text-[10px]">
          {data.emerging && data.emerging.length > 0 && (
            <span className="text-amber-400">emerging: {data.emerging.join(', ')}</span>
          )}
          {data.fading && data.fading.length > 0 && (
            <span className="text-zinc-500">fading: {data.fading.join(', ')}</span>
          )}
        </div>
      )}
    </div>
  )
}
