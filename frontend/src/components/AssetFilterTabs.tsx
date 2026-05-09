import type { AssetKind } from '../types'

const TABS: Array<{ label: string; value: AssetKind }> = [
  { label: 'All',    value: 'all'    },
  { label: 'Stocks', value: 'EQUITY' },
  { label: 'Crypto', value: 'CRYPTO' },
  { label: 'Forex',  value: 'FOREX'  },
]

function timeAgo(iso: string | null): string {
  if (!iso) return ''
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  return `${Math.round(mins / 60)}h ago`
}

interface Props {
  active: AssetKind
  onChange: (kind: AssetKind) => void
  updatedAt?: string | null
}

export function AssetFilterTabs({ active, onChange, updatedAt }: Props) {
  return (
    <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800 bg-zinc-900">
      <div className="flex gap-1">
        {TABS.map(tab => (
          <button
            key={tab.value}
            onClick={() => onChange(tab.value)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              active === tab.value
                ? 'bg-zinc-100 text-zinc-900'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {updatedAt && (
        <span className="text-[11px] text-zinc-500">Updated {timeAgo(updatedAt)}</span>
      )}
    </div>
  )
}
