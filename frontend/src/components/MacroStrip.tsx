import { useMacroStrip } from '../hooks/useMacroStrip'
import type { MacroTickerItem } from '../types'
import { Sparkline } from './Sparkline'

function MacroTile({ item }: { item: MacroTickerItem }) {
  const up = item.change_pct >= 0
  const fmtPrice = (v: number) => {
    if (v >= 10000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 })
    if (v >= 1000)  return v.toLocaleString(undefined, { maximumFractionDigits: 1 })
    if (v >= 100)   return v.toFixed(2)
    if (v >= 1)     return v.toFixed(2)
    return v.toFixed(4)
  }
  return (
    <div className="px-2 py-1.5 rounded-lg bg-zinc-900/60 border border-zinc-800">
      <div className="flex items-baseline justify-between gap-1">
        <span className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold truncate">{item.label}</span>
        <span className={'font-mono text-[10px] font-semibold shrink-0 ' + (up ? 'text-emerald-400' : 'text-rose-400')}>
          {up ? '+' : ''}{item.change_pct.toFixed(2)}%
        </span>
      </div>
      <div className="mt-0.5 flex items-center justify-between gap-2">
        <span className="font-mono text-sm text-zinc-100 font-bold truncate">{fmtPrice(item.price)}</span>
        <Sparkline data={item.sparkline} />
      </div>
    </div>
  )
}

export function MacroStrip() {
  const { data, loading } = useMacroStrip()
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-3">
      {loading ? (
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-12 rounded-lg bg-zinc-900 animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
          {data.map(item => <MacroTile key={item.label} item={item} />)}
        </div>
      )}
    </div>
  )
}
