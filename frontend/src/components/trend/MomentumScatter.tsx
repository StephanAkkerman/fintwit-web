import type { TrendTicker } from '../../types'
import { useElementWidth } from '../../hooks/useElementWidth'
import { INK, fmtCount, fmtGrowth, fmtNet, fmtPct, growth, priceChange, sentimentColor } from '../../utils/trendSummary'
import { TipRow, TipTitle, useChartTooltip } from './ChartTooltip'

// Growth axis is log2, from a quarter of the previous volume to 8×. Tickers
// beyond either end (including brand-new ones) are pinned to the edge.
const X_MIN = -2
const X_MAX = 3
const X_TICKS = [0.25, 0.5, 1, 2, 4, 8]
const Y_TICKS = [-1, -0.5, 0, 0.5, 1]

interface Props {
  tickers: TrendTicker[]
  onTickerClick?: (ticker: string) => void
}

export function MomentumScatter({ tickers, onTickerClick }: Props) {
  const [ref, W] = useElementWidth<HTMLDivElement>()
  const { show, hide, node } = useChartTooltip()
  const H = Math.max(300, Math.min(400, W * 0.62))
  const m = { l: 40, r: 16, t: 12, b: 34 }

  const lx = (g: number) => Math.min(X_MAX, Math.max(X_MIN, Number.isFinite(g) ? Math.log2(Math.max(g, 1e-9)) : X_MAX))
  const X = (g: number) => m.l + ((lx(g) - X_MIN) / (X_MAX - X_MIN)) * (W - m.l - m.r)
  const Y = (v: number) => m.t + (1 - (v + 1) / 2) * (H - m.t - m.b)

  const maxMentions = Math.max(1, ...tickers.map(t => t.mentions))
  const R = (v: number) => 5 + Math.sqrt(v / maxMentions) * (W < 500 ? 18 : 26)
  const points = tickers.map(t => {
    const g = growth(t)
    return { t, g, cx: X(g), cy: Y(t.net_sentiment ?? 0), r: R(t.mentions), isNew: !Number.isFinite(g) }
  })

  // Label every bubble that has room; the rest are named on hover. Larger
  // bubbles claim their spot first.
  type Box = { x: number; y: number; w: number; h: number }
  const placed: Box[] = []
  const hits = (a: Box) => placed.some(b => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h)
  const labels = points.map(p => {
    const w = p.t.ticker.length * 7 + 4
    const cands: [number, number][] = [
      ...(p.r > 14 ? [[p.cx, p.cy + 4] as [number, number]] : []),
      [p.cx, p.cy - p.r - 4], [p.cx, p.cy + p.r + 12], [p.cx + p.r + 4 + w / 2, p.cy + 4], [p.cx - p.r - 4 - w / 2, p.cy + 4],
    ]
    for (const [x, y] of cands) {
      const box = { x: x - w / 2, y: y - 10, w, h: 13 }
      if (hits(box) || box.x < m.l || box.x + box.w > W - m.r) continue
      placed.push(box)
      return { x, y, text: p.t.ticker }
    }
    return null
  })

  return (
    <div ref={ref} className="relative w-full">
      <svg width={W} height={H} role="img" aria-label="Mention growth against net sentiment per ticker" className="block overflow-visible">
        <rect x={X(1)} y={Y(1)} width={X(8) - X(1)} height={Y(0) - Y(1)} fill={INK.bull} opacity={0.05} />
        <rect x={X(1)} y={Y(0)} width={X(8) - X(1)} height={Y(-1) - Y(0)} fill={INK.bear} opacity={0.05} />
        {X_TICKS.map(v => (
          <g key={v}>
            <line x1={X(v)} x2={X(v)} y1={m.t} y2={H - m.b} stroke={INK.grid} strokeWidth={v === 1 ? 1.25 : 1} strokeDasharray={v === 1 ? undefined : '2 4'} />
            <text x={X(v)} y={H - m.b + 16} textAnchor="middle" fontSize={10} fill={INK.muted} className="font-mono">×{v}</text>
          </g>
        ))}
        {Y_TICKS.map(v => (
          <g key={v}>
            <line x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} stroke={INK.grid} strokeWidth={v === 0 ? 1.25 : 1} strokeDasharray={v === 0 ? undefined : '2 4'} />
            <text x={m.l - 6} y={Y(v) + 3} textAnchor="end" fontSize={10} fill={INK.muted} className="font-mono">{v === 0 ? '0' : fmtNet(v)}</text>
          </g>
        ))}
        <text x={W - m.r} y={H - 4} textAnchor="end" fontSize={10} fill={INK.muted} className="font-mono">mentions vs previous window →</text>
        <text x={W - m.r - 6} y={m.t + 14} textAnchor="end" fontSize={10} fontWeight={600} fill={INK.bull} className="font-mono">HEATING UP · BULLISH</text>
        <text x={W - m.r - 6} y={H - m.b - 8} textAnchor="end" fontSize={10} fontWeight={600} fill={INK.bear} className="font-mono">HEATING UP · BEARISH</text>
        <text x={m.l + 6} y={m.t + 14} fontSize={10} fontWeight={600} fill={INK.muted} className="font-mono">COOLING · STILL LIKED</text>
        <text x={m.l + 6} y={H - m.b - 8} fontSize={10} fontWeight={600} fill={INK.muted} className="font-mono">FADING</text>

        {points.map(p => {
          const c = sentimentColor(p.t.net_sentiment)
          const pc = priceChange(p.t)
          return (
            <g
              key={p.t.ticker}
              role="button"
              aria-label={`${p.t.ticker}: ${p.t.mentions} mentions, ${fmtGrowth(p.g)} vs previous window, net sentiment ${fmtNet(p.t.net_sentiment)}`}
              className="cursor-pointer"
              onClick={() => onTickerClick?.(p.t.ticker)}
              onMouseMove={e => show(e, (
                <>
                  <TipTitle>{p.t.ticker} <span className="font-normal text-zinc-500">{p.t.asset_kind.toLowerCase()}</span></TipTitle>
                  <TipRow label="mentions" value={fmtCount(p.t.mentions)} />
                  <TipRow label="vs previous" value={p.isNew ? 'new this window' : fmtGrowth(p.g)} />
                  <TipRow label="net sentiment" value={fmtNet(p.t.net_sentiment)} />
                  <TipRow label="accounts" value={p.t.unique_authors} />
                  {pc && <TipRow label="price" value={fmtPct(pc.change)} />}
                </>
              ))}
              onMouseLeave={hide}
            >
              <circle cx={p.cx} cy={p.cy} r={p.r} fill={c} fillOpacity={0.28} stroke={c} strokeWidth={1.5} strokeDasharray={p.isNew ? '3 2' : undefined} />
              <circle cx={p.cx} cy={p.cy} r={p.r + 1.5} fill="none" stroke={INK.card} strokeWidth={2} strokeOpacity={0.9} pointerEvents="none" />
            </g>
          )
        })}
        {labels.map((l, i) => l && (
          <text
            key={points[i].t.ticker}
            x={l.x} y={l.y} textAnchor="middle" fontSize={11} fontWeight={600} fill={INK.text}
            stroke={INK.card} strokeWidth={3} paintOrder="stroke" pointerEvents="none" className="font-mono"
          >
            {l.text}
          </text>
        ))}
      </svg>
      {node}
    </div>
  )
}
