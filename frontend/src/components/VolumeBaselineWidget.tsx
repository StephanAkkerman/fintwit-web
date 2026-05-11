import type { AssetKind } from '../types'
import { useVolumeBaseline } from '../hooks/useVolumeBaseline'

interface Props {
  assetKind: AssetKind
  windowHours?: number
  userFilter?: string | null
  subscriberOnly?: boolean
}

function sentimentBarColor(sentiment?: number): string {
  if (sentiment === undefined) return 'rgba(161,161,170,0.6)'
  if (sentiment > 0.1) return 'rgba(16,185,129,0.6)'
  if (sentiment < -0.1) return 'rgba(244,63,94,0.6)'
  return 'rgba(161,161,170,0.6)'
}

export function VolumeBaselineWidget({ assetKind, windowHours = 24, userFilter = null, subscriberOnly = false }: Props) {
  const { data, loading, error } = useVolumeBaseline(assetKind, windowHours, userFilter, subscriberOnly)

  if (loading) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 flex flex-col gap-3">
        <div className="h-4 w-32 bg-zinc-800 rounded animate-pulse" />
        {[0, 1, 2].map(i => (
          <div key={i} className="h-5 bg-zinc-800 rounded animate-pulse" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 text-zinc-500 text-sm">
        Failed to load volume data.
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 text-zinc-500 text-sm">
        No volume spikes detected.
      </div>
    )
  }

  const visible = data.slice(0, 10)
  const overflow = data.length - 10
  const maxMultiplier = Math.max(...data.map(d => d.volume_multiplier)) || 1

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 flex flex-col gap-0">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-[13px] font-semibold text-zinc-100">Unusually loud</h2>
        <span className="text-[10px] text-zinc-500 font-mono">today vs 7-day avg</span>
      </div>
      <div className="flex flex-col gap-2">
        {visible.map(item => {
          const fillWidth = `${Math.min(100, (item.volume_multiplier / maxMultiplier) * 100).toFixed(1)}%`
          const baselineWidth = `${Math.min(100, (item.baseline_7d_avg / Math.max(item.mentions_24h, 1)) * (item.volume_multiplier / maxMultiplier) * 100).toFixed(1)}%`
          return (
            <div key={item.ticker} className="grid items-center gap-2" style={{ gridTemplateColumns: '56px 1fr 44px' }}>
              <span className="font-mono text-[11px] text-zinc-100 font-semibold">${item.ticker}</span>
              <div className="relative h-[22px] rounded bg-zinc-900 border border-zinc-800 overflow-hidden">
                <div
                  className="absolute inset-y-0 left-0"
                  style={{ width: fillWidth, background: sentimentBarColor() }}
                />
                <div
                  className="absolute inset-y-0 left-0 bg-zinc-700/50"
                  style={{ width: baselineWidth }}
                />
                <div className="absolute inset-0 flex items-center px-2 font-mono text-[10px] text-zinc-100 font-bold">
                  {item.mentions_24h}
                  <span className="opacity-50 font-normal"> / {Math.round(item.baseline_7d_avg)}</span>
                </div>
              </div>
              <span className="font-mono text-[12px] font-bold text-zinc-100 text-right">
                {item.volume_multiplier.toFixed(1)}×
              </span>
            </div>
          )
        })}
      </div>
      {overflow > 0 && (
        <p className="font-mono text-zinc-500 text-[10px] mt-2">+{overflow} more</p>
      )}
    </div>
  )
}
