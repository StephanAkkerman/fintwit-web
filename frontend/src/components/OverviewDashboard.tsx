import { useState } from 'react'
import type { AssetKind } from '../types'
import { MacroStrip } from './MacroStrip'
import { AssetFilterTabs } from './AssetFilterTabs'
import { MentionHeatmap } from './MentionHeatmap'
import { SentimentShiftWidget } from './SentimentShiftWidget'
import { VolumeBaselineWidget } from './VolumeBaselineWidget'
import { HiddenGemWidget } from './HiddenGemWidget'

interface Props {
  onTickerClick?: (ticker: string) => void
}

export function OverviewDashboard({ onTickerClick }: Props) {
  const [assetKind, setAssetKind] = useState<AssetKind>('all')

  return (
    <div className="flex flex-col gap-4">
      <MacroStrip />
      <AssetFilterTabs active={assetKind} onChange={setAssetKind} />
      <MentionHeatmap assetKind={assetKind} onTickerClick={onTickerClick} />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <SentimentShiftWidget assetKind={assetKind} />
        <VolumeBaselineWidget assetKind={assetKind} />
        <HiddenGemWidget assetKind={assetKind} />
      </div>
    </div>
  )
}
