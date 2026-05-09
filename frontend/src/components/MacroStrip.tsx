import { useMacroStrip } from '../hooks/useMacroStrip'
import type { MacroTickerItem } from '../types'

function Sparkline({ data, up }: { data: number[]; up: boolean }) {
  if (data.length < 2) return null
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const W = 56, H = 20
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * W
    const y = H - ((v - min) / range) * (H - 2) - 1
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return (
    <svg width={W} height={H} className="shrink-0">
      <polyline points={pts} fill="none"
        stroke={up ? '#34d399' : '#f87171'} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  )
}

function MacroTicker({ item }: { item: MacroTickerItem }) {
  const up = item.change_pct >= 0
  return (
    <div className="flex items-center gap-2 px-4 py-2 shrink-0">
      <span className="text-xs font-semibold text-zinc-300 w-10 shrink-0">{item.label}</span>
      <Sparkline data={item.sparkline} up={up} />
      <div className="flex flex-col items-end min-w-[72px]">
        <span className="text-xs font-mono text-zinc-100 leading-tight">
          {item.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
        </span>
        <span className={`text-[11px] font-mono leading-tight ${up ? 'text-emerald-400' : 'text-rose-400'}`}>
          {up ? '+' : ''}{item.change_pct.toFixed(2)}%
        </span>
      </div>
    </div>
  )
}

export function MacroStrip() {
  const { data, loading } = useMacroStrip()
  return (
    <div className="w-full bg-zinc-950 border-b border-zinc-800 overflow-x-auto">
      <div className="flex items-center divide-x divide-zinc-800">
        {loading && (
          <span className="px-4 py-2 text-xs text-zinc-500 animate-pulse">Loading…</span>
        )}
        {data.map(item => <MacroTicker key={item.label} item={item} />)}
      </div>
    </div>
  )
}
