import { useState, type ReactNode } from 'react'
import type { AssetKind, TrendSummary, TrendWindow } from '../types'
import { useTrendSummary } from '../hooks/useTrendSummary'
import { AssetFilterTabs } from './AssetFilterTabs'
import { TrendHeadline } from './trend/TrendHeadline'
import { MomentumScatter } from './trend/MomentumScatter'
import { RankRace } from './trend/RankRace'
import { SentimentTimeline } from './trend/SentimentTimeline'
import { ChatterVsPrice } from './trend/ChatterVsPrice'
import { TREND_WINDOWS, TREND_WINDOW_LABEL } from '../utils/trendSummary'

const SCOPE_LABEL: Record<AssetKind, string> = {
  all:    'All markets',
  EQUITY: 'Stocks',
  CRYPTO: 'Crypto',
  FOREX:  'Forex',
}

const PREV_LABEL: Record<TrendWindow, string> = { '1d': 'previous 24h', '7d': 'previous 7d', '30d': 'previous 30d' }

function Card({ title, hint, label, children }: { title: string; hint: string; label: string; children: ReactNode }) {
  return (
    <section aria-label={label} className="min-w-0 rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="mb-2.5">
        <h2 className="text-[13px] font-semibold text-zinc-100">{title}</h2>
        <p className="mt-0.5 text-[11px] leading-snug text-zinc-500">{hint}</p>
      </div>
      {children}
    </section>
  )
}

/** Flag a window that reaches back further than the stored tweets do. */
function coverageNote(data: TrendSummary): string | null {
  if (!data.data_since || data.buckets.length === 0) return null
  const since = new Date(data.data_since).getTime()
  const start = new Date(data.buckets[0]).getTime()
  const prevStart = start - (Date.now() - start)
  if (since <= prevStart) return null
  const days = Math.max(0, (Date.now() - since) / 86_400_000)
  const span = days < 1 ? `${Math.max(1, Math.round(days * 24))} hours` : `${days.toFixed(days < 10 ? 1 : 0)} days`
  return since > start
    ? `Only ${span} of tweets are stored, so this window is partly empty and the comparison with the ${PREV_LABEL[data.window]} is not meaningful yet.`
    : `Only ${span} of tweets are stored, so the ${PREV_LABEL[data.window]} is incomplete and growth figures run high.`
}

function Skeleton() {
  return (
    <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading trend summary">
      <div className="h-[190px] animate-pulse rounded-2xl bg-zinc-900" />
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="h-[400px] animate-pulse rounded-2xl bg-zinc-900" />
        <div className="h-[400px] animate-pulse rounded-2xl bg-zinc-900" />
      </div>
    </div>
  )
}

interface Props {
  onTickerClick?: (ticker: string) => void
  userFilter?: string | null
  subscriberOnly?: boolean
}

export function OverviewDashboard({ onTickerClick, userFilter = null, subscriberOnly = false }: Props) {
  const [assetKind, setAssetKind] = useState<AssetKind>('all')
  const [trendWindow, setTrendWindow] = useState<TrendWindow>('7d')
  const { data, loading, error } = useTrendSummary(trendWindow, assetKind, userFilter, subscriberOnly)

  let body: ReactNode
  if (loading && !data) {
    body = <Skeleton />
  } else if (error || !data) {
    body = (
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-500">
        Couldn't load the trend summary. Check that the backend is running, then reload the page.
      </div>
    )
  } else {
    const note = coverageNote(data)
    body = (
      <div className={`flex flex-col gap-3 transition-opacity ${loading ? 'opacity-60' : ''}`}>
        {note && (
          <p className="rounded-xl border border-dashed border-zinc-800 px-3 py-2 text-[12px] text-zinc-500">{note}</p>
        )}
        <TrendHeadline data={data} assetKind={assetKind} onTickerClick={onTickerClick} />
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
          <Card
            label="Momentum and sentiment"
            title="Momentum × sentiment"
            hint="Right means more mentions than the previous window. Up means more bullish. Bubble size shows mention count; a dashed outline marks a ticker that is new this window."
          >
            <MomentumScatter tickers={data.tickers} onTickerClick={onTickerClick} />
          </Card>
          <Card
            label="Mention rank over time"
            title="Rank race"
            hint="Mention rank of the current top 8 over the window. A steep climb marks a ticker on the rise."
          >
            <RankRace tickers={data.tickers} buckets={data.buckets} window={data.window} onTickerClick={onTickerClick} />
          </Card>
        </div>
        <Card
          label="Sentiment timeline"
          title="Sentiment timeline"
          hint="Rows are the 10 most-mentioned tickers. Colour shows net sentiment for each time slot, and fainter cells had fewer mentions."
        >
          <SentimentTimeline tickers={data.tickers} buckets={data.buckets} window={data.window} onTickerClick={onTickerClick} />
        </Card>
        <Card
          label="Chatter versus price"
          title="Chatter vs price"
          hint="For each top ticker, the line shows the price quoted in its tweets and the bars show mentions coloured by sentiment. Click a ticker to open its detail view."
        >
          <ChatterVsPrice tickers={data.tickers} buckets={data.buckets} window={data.window} onTickerClick={onTickerClick} />
        </Card>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="mr-auto">
          <h2 className="text-lg font-bold leading-tight text-zinc-100">
            {SCOPE_LABEL[assetKind]} · trend summary
          </h2>
          <p className="mt-0.5 font-mono text-[10px] text-zinc-500">
            sentiment from FinTwitBERT · {TREND_WINDOW_LABEL[trendWindow]} · compared with the {PREV_LABEL[trendWindow]}
          </p>
        </div>

        <AssetFilterTabs active={assetKind} onChange={setAssetKind} />

        <div role="tablist" aria-label="Timeframe" className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-900 p-0.5">
          {TREND_WINDOWS.map(w => (
            <button
              key={w}
              role="tab"
              aria-selected={trendWindow === w}
              onClick={() => setTrendWindow(w)}
              className={
                'rounded-md px-3 py-1 text-[11px] font-semibold transition-colors ' +
                (trendWindow === w ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200')
              }
            >
              {w}
            </button>
          ))}
        </div>
      </div>

      {body}
    </div>
  )
}
