import { useState } from 'react'
import type { AssetKind } from '../types'
import type { PortfolioTickerLookup } from '../hooks/usePortfolioTickers'
import { MacroStrip } from './MacroStrip'
import MarketOverview from './MarketOverview'
import { AssetFilterTabs } from './AssetFilterTabs'
import { MentionHeatmap, MENTION_WINDOWS, type MentionWindowHours } from './MentionHeatmap'
import { RedditTrendsWidget } from './RedditTrendsWidget'
import { SentimentShiftWidget } from './SentimentShiftWidget'
import { VolumeBaselineWidget } from './VolumeBaselineWidget'
import { HiddenGemWidget } from './HiddenGemWidget'
import { SectorMentionsWidget } from './SectorMentionsWidget'

const SCOPE_LABEL: Record<AssetKind, string> = {
  all:    'All markets',
  EQUITY: 'Stocks',
  CRYPTO: 'Crypto',
  FOREX:  'Forex',
}

function windowLabel(h: MentionWindowHours): string {
  return h < 48 ? `${h}h` : `${h / 24}d`
}

interface Props {
  onTickerClick?: (ticker: string) => void
  userFilter?: string | null
  subscriberOnly?: boolean
  portfolioLookup?: PortfolioTickerLookup
}

export function OverviewDashboard({ onTickerClick, userFilter = null, subscriberOnly = false, portfolioLookup }: Props) {
  const [assetKind, setAssetKind]     = useState<AssetKind>('all')
  const [windowHours, setWindowHours] = useState<MentionWindowHours>(MENTION_WINDOWS[0])

  return (
    <div className="flex flex-col gap-3">
      <MacroStrip />
      <MarketOverview />

      {/* Dashboard header */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="mr-auto">
          <h2 className="text-lg font-bold text-zinc-100 leading-tight">
            {SCOPE_LABEL[assetKind]} · overview
          </h2>
          <p className="text-[10px] text-zinc-500 font-mono mt-0.5">
            sentiment from FinTwitBERT · {windowLabel(windowHours)} window
          </p>
        </div>

        <AssetFilterTabs active={assetKind} onChange={setAssetKind} />

        {/* Window selector */}
        <div role="tablist" aria-label="Lookback window" className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-900 p-0.5">
          {MENTION_WINDOWS.map(h => (
            <button
              key={h}
              role="tab"
              aria-selected={windowHours === h}
              onClick={() => setWindowHours(h)}
              className={
                'rounded-md px-3 py-1 text-[11px] font-semibold transition-colors ' +
                (windowHours === h
                  ? 'bg-zinc-700 text-zinc-100'
                  : 'text-zinc-400 hover:text-zinc-200')
              }
            >
              {windowLabel(h)}
            </button>
          ))}
        </div>
      </div>

      <MentionHeatmap
        assetKind={assetKind}
        windowHours={windowHours}
        onWindowChange={setWindowHours}
        onTickerClick={onTickerClick}
        height={320}
        userFilter={userFilter}
        subscriberOnly={subscriberOnly}
      />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <SentimentShiftWidget assetKind={assetKind} windowHours={windowHours} userFilter={userFilter} subscriberOnly={subscriberOnly} portfolioLookup={portfolioLookup} />
        <VolumeBaselineWidget assetKind={assetKind} windowHours={windowHours} userFilter={userFilter} subscriberOnly={subscriberOnly} portfolioLookup={portfolioLookup} />
        <HiddenGemWidget assetKind={assetKind} windowHours={windowHours} userFilter={userFilter} subscriberOnly={subscriberOnly} portfolioLookup={portfolioLookup} />
      </div>

      {/* Reddit is its own source: the asset-kind/window/user controls above
          filter tweets, and none of them apply to a subreddit scrape. */}
      <RedditTrendsWidget portfolioLookup={portfolioLookup} onTickerSelect={onTickerClick} />

      {/* Equity-only: sector/industry metadata is resolved for stocks/ETFs, not crypto or forex. */}
      <SectorMentionsWidget windowHours={windowHours} userFilter={userFilter} subscriberOnly={subscriberOnly} onTickerClick={onTickerClick} />
    </div>
  )
}
