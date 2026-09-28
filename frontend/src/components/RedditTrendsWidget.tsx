import type { ReactNode } from 'react'
import { AlertTriangle, MessagesSquare } from 'lucide-react'
import type { RedditTickerTrend, RedditTrendReport, RedditTrendWorkerStatus } from '../types'
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

function formatAgo(iso: string | null | undefined): string {
  if (!iso) return 'never'
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000))
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

function formatIn(iso: string | null | undefined): string | null {
  if (!iso) return null
  const seconds = Math.floor((new Date(iso).getTime() - Date.now()) / 1000)
  if (seconds <= 60) return 'shortly'
  if (seconds < 3600) return `in ${Math.ceil(seconds / 60)}m`
  return `in ${Math.round(seconds / 3600)}h`
}

// Hourly mentions across the window, so a row shows *when* a ticker got loud
// and not just how loud it got in total.
function Sparkline({ series }: { series: number[] }) {
  if (series.length < 2) return null
  const width = 48
  const height = 14
  const peak = Math.max(...series, 1)
  const step = width / (series.length - 1)
  const points = series
    .map((value, i) => `${(i * step).toFixed(1)},${(height - (value / peak) * (height - 2) - 1).toFixed(1)}`)
    .join(' ')
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="shrink-0 text-zinc-400"
      aria-hidden="true"
      data-testid="reddit-sparkline"
    >
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round" />
    </svg>
  )
}

function Notice({ children, tone = 'muted' }: { children: ReactNode; tone?: 'muted' | 'warn' }) {
  const Icon = tone === 'warn' ? AlertTriangle : MessagesSquare
  return (
    <div className="flex items-start gap-2 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-500">
      <Icon
        className={`mt-0.5 h-4 w-4 shrink-0 ${tone === 'warn' ? 'text-amber-400' : ''}`}
        aria-hidden="true"
      />
      <div className="min-w-0 space-y-1">{children}</div>
    </div>
  )
}

function WorkerError({ worker }: { worker: RedditTrendWorkerStatus }) {
  const retry = formatIn(worker.next_attempt_at)
  return (
    <>
      {worker.last_error && (
        <p className="break-words font-mono text-[11px] text-zinc-400">{worker.last_error}</p>
      )}
      <p className="text-[11px] text-zinc-600">
        Last attempt {formatAgo(worker.last_attempt_at)}
        {retry ? ` · retrying ${retry}` : ''}. The server log has the full traceback.
      </p>
    </>
  )
}

// Why there are no stored results yet. The worker status is what separates
// "still loading models" from "every scrape fails" — both used to read as
// "waiting for the first scrape" indefinitely.
function NoRunYet({ worker }: { worker?: RedditTrendWorkerStatus }) {
  switch (worker?.state) {
    case 'disabled':
      return <Notice>Reddit trend worker is turned off (REDDIT_TRENDS_ENABLED).</Notice>
    case 'warming_up':
      return <Notice>Loading the ticker and sentiment models before the first Reddit scrape…</Notice>
    case 'scraping':
      return <Notice>Scraping subreddits for the first trend report…</Notice>
    case 'error':
      return (
        <Notice tone="warn">
          <p className="text-zinc-300">The Reddit trend scrape is failing.</p>
          <WorkerError worker={worker} />
        </Notice>
      )
    case 'empty':
      return (
        <Notice tone="warn">
          <p className="text-zinc-300">The last Reddit scrape returned no posts.</p>
          <WorkerError worker={worker} />
        </Notice>
      )
    default:
      return <Notice>Waiting for the first Reddit scrape.</Notice>
  }
}

function Row({
  item,
  maxMentions,
  series,
  portfolioStatus,
  onTickerSelect,
}: {
  item: RedditTickerTrend
  maxMentions: number
  series?: number[]
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
        {series && <Sparkline series={series} />}
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

interface CardProps extends Omit<Props, 'limit'> {
  data: RedditTrendReport
  loading: boolean
  error: boolean
}

/** The ranking itself, for callers that already hold the trend report. */
export function RedditTrendsCard({ data, loading, error, portfolioLookup, onTickerSelect }: CardProps) {
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
    return <Notice>Failed to load Reddit trends.</Notice>
  }

  // Distinct empty states, because the fix for each is different: install the
  // package, fix whatever the worker is failing on, wait for the first run, or
  // nothing is being discussed.
  if (!data.available) {
    return <Notice>Reddit trend analysis is not enabled in this deployment.</Notice>
  }

  if (!data.captured_at) {
    return <NoRunYet worker={data.worker} />
  }

  if (data.tickers.length === 0) {
    return <Notice>No tickers recognised in the latest scrape.</Notice>
  }

  const maxMentions = Math.max(...data.tickers.map((t) => t.mentions), 0)
  const series = data.timeline?.series ?? {}
  const worker = data.worker
  const refreshFailing = worker?.state === 'error' || worker?.state === 'empty'
  const emerging = data.emerging ?? []
  const fading = data.fading ?? []

  return (
    <div className="flex flex-col gap-0 rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-[13px] font-semibold text-zinc-100">Reddit Trends</h2>
        <span className="font-mono text-[10px] text-zinc-500">
          {data.subreddits.length} subs · {formatAgo(data.captured_at)}
        </span>
      </div>
      {refreshFailing && worker && (
        <div className="mb-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-300">
          Refresh failing — showing the run from {formatAgo(data.captured_at)}.
          {worker.last_error && (
            <span className="mt-0.5 block break-words font-mono text-[10px] text-amber-200/80">
              {worker.last_error}
            </span>
          )}
        </div>
      )}
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
            series={series[item.symbol]}
            portfolioStatus={portfolioLookup?.(item.symbol) ?? null}
            onTickerSelect={onTickerSelect}
          />
        ))}
      </div>
      {(emerging.length > 0 || fading.length > 0) && (
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 border-t border-zinc-900 pt-2 font-mono text-[10px]">
          {emerging.length > 0 && (
            <span className="text-amber-400">emerging: {emerging.join(', ')}</span>
          )}
          {fading.length > 0 && <span className="text-zinc-500">fading: {fading.join(', ')}</span>}
        </div>
      )}
    </div>
  )
}

export function RedditTrendsWidget({ limit = 10, portfolioLookup, onTickerSelect }: Props) {
  const { data, loading, error } = useRedditTrends(limit)
  return (
    <RedditTrendsCard
      data={data}
      loading={loading}
      error={error}
      portfolioLookup={portfolioLookup}
      onTickerSelect={onTickerSelect}
    />
  )
}
