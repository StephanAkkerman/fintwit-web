import { useCallback, useState, type MouseEvent, type ReactNode } from 'react'

interface TipState { x: number; y: number; content: ReactNode }

/** A cursor-following tooltip shared by the trend charts. */
export function useChartTooltip() {
  const [tip, setTip] = useState<TipState | null>(null)

  const show = useCallback((e: MouseEvent, content: ReactNode) => {
    setTip({ x: e.clientX, y: e.clientY, content })
  }, [])
  const hide = useCallback(() => setTip(null), [])

  const vw = typeof window !== 'undefined' ? window.innerWidth : 1e4
  const vh = typeof window !== 'undefined' ? window.innerHeight : 1e4
  // Near the bottom edge, open upwards so the tooltip stays on screen.
  const flipUp = tip ? tip.y > vh - 160 : false

  const node = tip ? (
    <div
      role="tooltip"
      className="pointer-events-none fixed z-50 max-w-[240px] rounded-lg border border-zinc-800 bg-zinc-900 px-2.5 py-2 font-mono text-[11px] leading-relaxed text-zinc-100 shadow-xl"
      style={{
        left: Math.max(8, Math.min(tip.x + 14, vw - 250)),
        top: flipUp ? tip.y - 14 : tip.y + 14,
        transform: flipUp ? 'translateY(-100%)' : undefined,
      }}
    >
      {tip.content}
    </div>
  ) : null

  return { show, hide, node }
}

export function TipTitle({ children }: { children: ReactNode }) {
  return <div className="mb-0.5 font-semibold">{children}</div>
}

export function TipRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 text-zinc-400">
      <span>{label}</span>
      <span className="text-zinc-100">{value}</span>
    </div>
  )
}
