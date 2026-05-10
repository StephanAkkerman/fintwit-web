import type { AssetKind } from '../types'

const TABS: Array<{ label: string; value: AssetKind }> = [
  { label: 'All',    value: 'all'    },
  { label: 'Stocks', value: 'EQUITY' },
  { label: 'Crypto', value: 'CRYPTO' },
  { label: 'Forex',  value: 'FOREX'  },
]

interface Props {
  active: AssetKind
  onChange: (kind: AssetKind) => void
}

export function AssetFilterTabs({ active, onChange }: Props) {
  return (
    <div className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-900 p-0.5">
      {TABS.map(tab => (
        <button
          key={tab.value}
          onClick={() => onChange(tab.value)}
          className={
            'rounded-md px-3 py-1 text-[11px] font-semibold transition-colors ' +
            (active === tab.value
              ? 'bg-zinc-100 text-zinc-900'
              : 'text-zinc-300 hover:bg-zinc-800')
          }
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
