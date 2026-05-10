import { useState } from 'react'
import type { AssetKind } from '../types'
import { MacroStrip } from './MacroStrip'
import { AssetFilterTabs } from './AssetFilterTabs'
import { MentionHeatmap, MENTION_WINDOWS, type MentionWindowHours } from './MentionHeatmap'
import { SentimentShiftWidget } from './SentimentShiftWidget'
import { VolumeBaselineWidget } from './VolumeBaselineWidget'
import { HiddenGemWidget } from './HiddenGemWidget'

type Layout = 'newspaper' | 'grid' | 'stream'

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
}

export function OverviewDashboard({ onTickerClick }: Props) {
  const [assetKind, setAssetKind]   = useState<AssetKind>('all')
  const [windowHours, setWindowHours] = useState<MentionWindowHours>(MENTION_WINDOWS[0])
  const [layout, setLayout]         = useState<Layout>('newspaper')

  const heatHeight = layout === 'newspaper' ? 320 : layout === 'grid' ? 280 : 220

  const widgets = (
    <>
      <SentimentShiftWidget assetKind={assetKind} windowHours={windowHours} />
      <VolumeBaselineWidget assetKind={assetKind} windowHours={windowHours} />
      <HiddenGemWidget assetKind={assetKind} windowHours={windowHours} />
    </>
  )

  return (
    <div className="flex flex-col gap-3">
      <MacroStrip />

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

        {/* Layout switcher */}
        <div className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-900 p-0.5">
          {([['newspaper', 'News'], ['grid', 'Grid'], ['stream', 'Stream']] as const).map(([k, l]) => (
            <button
              key={k}
              onClick={() => setLayout(k)}
              className={
                'rounded-md px-2 py-1 text-[11px] font-semibold transition-colors ' +
                (layout === k
                  ? 'bg-zinc-100 text-zinc-900'
                  : 'text-zinc-300 hover:bg-zinc-800')
              }
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      {/* Newspaper: full-width heat → 3-col widgets */}
      {layout === 'newspaper' && (
        <>
          <MentionHeatmap
            assetKind={assetKind}
            windowHours={windowHours}
            onWindowChange={setWindowHours}
            onTickerClick={onTickerClick}
            height={heatHeight}
          />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {widgets}
          </div>
        </>
      )}

      {/* Grid: heat left (7) + stacked widgets right (5) */}
      {layout === 'grid' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
          <div className="lg:col-span-7">
            <MentionHeatmap
              assetKind={assetKind}
              windowHours={windowHours}
              onWindowChange={setWindowHours}
              onTickerClick={onTickerClick}
              height={heatHeight}
            />
          </div>
          <div className="lg:col-span-5 flex flex-col gap-3">
            {widgets}
          </div>
        </div>
      )}

      {/* Stream: compact heat → 3-col widgets */}
      {layout === 'stream' && (
        <>
          <MentionHeatmap
            assetKind={assetKind}
            windowHours={windowHours}
            onWindowChange={setWindowHours}
            onTickerClick={onTickerClick}
            height={heatHeight}
          />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {widgets}
          </div>
        </>
      )}
    </div>
  )
}
