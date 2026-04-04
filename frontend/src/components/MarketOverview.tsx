import { useMarketAssets } from '../hooks/useMarketAssets'
import AssetBadge from './AssetBadge'

export default function MarketOverview() {
  const { assets } = useMarketAssets()

  if (assets.length === 0) return null

  return (
    <div className="bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-4 flex flex-col space-y-3 mb-4">
      <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider">Top Streamed Assets</h2>
      <div className="flex flex-wrap gap-2">
        {assets.map((asset) => (
          <AssetBadge key={asset.symbol} asset={asset} />
        ))}
      </div>
    </div>
  )
}
