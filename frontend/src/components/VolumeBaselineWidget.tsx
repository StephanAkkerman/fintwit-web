import type { AssetKind } from '../types'
import { useVolumeBaseline } from '../hooks/useVolumeBaseline'

interface Props {
  assetKind: AssetKind
}

export function VolumeBaselineWidget({ assetKind }: Props) {
  const { data, loading, error } = useVolumeBaseline(assetKind)

  if (loading) {
    return (
      <div className="bg-zinc-900 rounded-2xl p-4 flex flex-col gap-3">
        <div className="h-4 w-32 bg-zinc-800 rounded animate-pulse" />
        {[0, 1, 2].map(i => (
          <div key={i} className="h-4 bg-zinc-800 rounded animate-pulse" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-zinc-900 rounded-2xl p-4 text-zinc-500 text-sm">
        Failed to load volume data.
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="bg-zinc-900 rounded-2xl p-4 text-zinc-500 text-sm">
        No volume spikes detected.
      </div>
    )
  }

  const visible = data.slice(0, 10)
  const overflow = data.length - 10
  const maxMultiplier = Math.max(...data.map(d => d.volume_multiplier))

  return (
    <div className="bg-zinc-900 rounded-2xl p-4 flex flex-col gap-3">
      <h2 className="text-zinc-100 text-sm font-semibold">Volume Spike</h2>
      {visible.map(item => {
        const barWidth = `${Math.min(100, (item.volume_multiplier / maxMultiplier) * 100).toFixed(1)}%`
        return (
          <div key={item.ticker} className="flex items-center gap-2">
            <span className="text-zinc-100 text-sm font-mono w-16 shrink-0">{item.ticker}</span>
            <div className="flex-1 bg-zinc-800 rounded-full h-1.5 overflow-hidden">
              <div
                className="h-full bg-amber-500 rounded-full"
                style={{ width: barWidth }}
              />
            </div>
            <span className="text-amber-400 text-xs font-mono shrink-0">
              +{item.volume_multiplier.toFixed(1)}×
            </span>
          </div>
        )
      })}
      {overflow > 0 && (
        <p className="text-zinc-500 text-xs">+{overflow} more</p>
      )}
    </div>
  )
}
