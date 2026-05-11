import { useHiddenGems } from '../hooks/useHiddenGems'
import type { AssetKind } from '../types'

interface Props {
  assetKind: AssetKind
  windowHours?: number
  userFilter?: string | null
  subscriberOnly?: boolean
}

interface GemBadgeProps {
  subtype: 'new' | 'resurfacing'
}

function GemBadge({ subtype }: GemBadgeProps) {
  if (subtype === 'new') {
    return (
      <span className="font-mono bg-violet-950 text-violet-300 text-[10px] font-semibold px-1.5 py-0.5 rounded">
        ✦ new
      </span>
    )
  }
  return (
    <span className="font-mono bg-sky-950 text-sky-300 text-[10px] font-semibold px-1.5 py-0.5 rounded">
      ↩ resurface
    </span>
  )
}

export function HiddenGemWidget({ assetKind, windowHours = 24, userFilter = null, subscriberOnly = false }: Props) {
  const { data, loading, error } = useHiddenGems(assetKind, windowHours, userFilter, subscriberOnly)

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
        Failed to load hidden gems.
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 text-zinc-500 text-sm">
        No hidden gems found.
      </div>
    )
  }

  const visible = data.slice(0, 10)
  const remaining = data.length - 10

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 flex flex-col gap-0">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-[13px] font-semibold text-zinc-100">Hidden gems</h2>
        <span className="text-[10px] text-zinc-500 font-mono">low-vol tickers gaining traction</span>
      </div>
      <div className="flex flex-col">
        {visible.map((item, i) => (
          <div
            key={item.ticker}
            className={'flex items-center justify-between py-1.5 ' + (i < visible.length - 1 ? 'border-b border-zinc-900' : '')}
          >
            <span className="font-mono text-[11px] text-zinc-100 font-semibold">${item.ticker}</span>
            <span className="flex items-center gap-1.5">
              <GemBadge subtype={item.gem_subtype} />
              {item.gem_subtype === 'new' && (
                <span className="font-mono text-zinc-500 text-[10px]">first time</span>
              )}
              {item.gem_subtype === 'resurfacing' && item.days_since_last !== null && (
                <span className="font-mono text-zinc-500 text-[10px]">{item.days_since_last}d ago</span>
              )}
            </span>
          </div>
        ))}
      </div>
      {remaining > 0 && (
        <p className="font-mono text-zinc-500 text-[10px] mt-2">+{remaining} more</p>
      )}
    </div>
  )
}
