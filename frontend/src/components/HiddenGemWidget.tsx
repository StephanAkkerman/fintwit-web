import { useHiddenGems } from '../hooks/useHiddenGems'
import type { AssetKind } from '../types'

interface Props {
  assetKind: AssetKind
}

interface GemBadgeProps {
  subtype: 'new' | 'resurfacing'
}

function GemBadge({ subtype }: GemBadgeProps) {
  if (subtype === 'new') {
    return (
      <span className="bg-violet-950 text-violet-300 text-xs font-medium px-1.5 py-0.5 rounded">
        ✦ new
      </span>
    )
  }
  return (
    <span className="bg-sky-950 text-sky-300 text-xs font-medium px-1.5 py-0.5 rounded">
      ↩ resurface
    </span>
  )
}

export function HiddenGemWidget({ assetKind }: Props) {
  const { data, loading, error } = useHiddenGems(assetKind)

  if (loading) {
    return (
      <div className="bg-zinc-900 rounded-2xl p-4 flex flex-col gap-3">
        <div className="h-4 w-32 bg-zinc-800 rounded animate-pulse" />
        {[0, 1, 2].map(i => (
          <div key={i} className="h-5 bg-zinc-800 rounded animate-pulse" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-zinc-900 rounded-2xl p-4 text-zinc-500 text-sm">
        Failed to load hidden gems.
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="bg-zinc-900 rounded-2xl p-4 text-zinc-500 text-sm">
        No hidden gems found.
      </div>
    )
  }

  const visible = data.slice(0, 10)
  const remaining = data.length - 10

  return (
    <div className="bg-zinc-900 rounded-2xl p-4 flex flex-col gap-3">
      <h2 className="text-zinc-100 text-sm font-semibold">Hidden Gems</h2>
      {visible.map(item => (
        <div key={item.ticker} className="flex items-center justify-between">
          <span className="text-zinc-100 text-sm font-mono">{item.ticker}</span>
          <span className="flex items-center gap-1.5">
            <GemBadge subtype={item.gem_subtype} />
            {item.gem_subtype === 'new' && (
              <span className="text-zinc-500 text-xs">first time</span>
            )}
            {item.gem_subtype === 'resurfacing' && item.days_since_last !== null && (
              <span className="text-zinc-500 text-xs">{item.days_since_last}d ago</span>
            )}
          </span>
        </div>
      ))}
      {remaining > 0 && (
        <p className="text-zinc-500 text-xs">+{remaining} more</p>
      )}
    </div>
  )
}
