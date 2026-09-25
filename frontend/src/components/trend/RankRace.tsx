import { useState } from 'react'
import type { TrendTicker, TrendWindow } from '../../types'
import { useElementWidth } from '../../hooks/useElementWidth'
import { INK, assignSeriesColors, formatBucket, ranksOverTime, smoothingFor } from '../../utils/trendSummary'
import { TipRow, TipTitle, useChartTooltip } from './ChartTooltip'

const SHOWN = 8
const MAX_RANK = 10

interface Props {
  tickers: TrendTicker[]
  buckets: string[]
  window: TrendWindow
  onTickerClick?: (ticker: string) => void
}

export function RankRace({ tickers, buckets, window: win, onTickerClick }: Props) {
  const [ref, W] = useElementWidth<HTMLDivElement>()
  const { show, hide, node } = useChartTooltip()
  const [focus, setFocus] = useState<string | null>(null)

  const n = buckets.length
  if (n < 2 || tickers.length === 0) {
    return <div ref={ref} className="py-10 text-center text-sm text-zinc-500">Not enough activity to rank yet.</div>
  }

  const ranks = ranksOverTime(tickers, smoothingFor(n))
  const top = [...tickers].sort((a, b) => ranks.get(a.ticker)![n - 1] - ranks.get(b.ticker)![n - 1]).slice(0, SHOWN)
  const colors = assignSeriesColors(top.map(t => t.ticker))

  const H = Math.max(300, Math.min(400, W * 0.9))
  const m = { l: 26, r: 52, t: 10, b: 26 }
  const X = (i: number) => m.l + (i / (n - 1)) * (W - m.l - m.r)
  // Ranks below the chart floor collapse onto a band just under rank 10.
  const Y = (r: number) => m.t + ((Math.min(r, MAX_RANK + 0.6) - 1) / (MAX_RANK - 0.4)) * (H - m.t - m.b)
  const ticks = [0, Math.floor((n - 1) / 3), Math.floor((2 * (n - 1)) / 3), n - 1]

  return (
    <div ref={ref} className="relative w-full">
      <svg width={W} height={H} role="img" aria-label="Mention rank over time for the top tickers" className="block overflow-visible">
        {Array.from({ length: MAX_RANK }, (_, k) => k + 1).map(r => (
          <g key={r}>
            <line x1={m.l} x2={W - m.r} y1={Y(r)} y2={Y(r)} stroke={INK.grid} strokeDasharray="2 4" />
            <text x={m.l - 8} y={Y(r) + 3} textAnchor="end" fontSize={10} fill={INK.muted} className="font-mono">{r}</text>
          </g>
        ))}
        {ticks.map(i => (
          <text
            key={i} x={X(i)} y={H - 8} fontSize={10} fill={INK.muted} className="font-mono"
            textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}
          >
            {i === n - 1 ? 'now' : formatBucket(buckets[i], win)}
          </text>
        ))}
        {top.map(t => {
          const rk = ranks.get(t.ticker)!
          const pts = rk.map((r, i) => `${X(i)},${Y(r)}`).join(' ')
          const c = colors[t.ticker]
          const start = rk[0], end = rk[n - 1], delta = start - end
          return (
            <g
              key={t.ticker}
              className="cursor-pointer transition-opacity"
              style={{ opacity: focus && focus !== t.ticker ? 0.15 : 1 }}
              onMouseEnter={() => setFocus(t.ticker)}
              onMouseLeave={() => { setFocus(null); hide() }}
              onMouseMove={e => show(e, (
                <>
                  <TipTitle>{t.ticker}</TipTitle>
                  <TipRow label="rank now" value={`#${end}`} />
                  <TipRow label="rank at start" value={`#${start}${start > MAX_RANK ? ' (off chart)' : ''}`} />
                  <TipRow label="change" value={delta > 0 ? `▲ ${delta}` : delta < 0 ? `▼ ${-delta}` : 'no change'} />
                </>
              ))}
              onClick={() => onTickerClick?.(t.ticker)}
            >
              <polyline points={pts} fill="none" stroke="transparent" strokeWidth={12} />
              <polyline points={pts} fill="none" stroke={c} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              <circle cx={X(n - 1)} cy={Y(end)} r={4} fill={c} stroke={INK.card} strokeWidth={2} />
              <text x={X(n - 1) + 9} y={Y(end) + 4} fontSize={11} fontWeight={600} fill={INK.text} className="font-mono">{t.ticker}</text>
            </g>
          )
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1.5 font-mono text-[11px] text-zinc-400">
        {top.map(t => (
          <span
            key={t.ticker}
            className="inline-flex items-center gap-1.5"
            onMouseEnter={() => setFocus(t.ticker)}
            onMouseLeave={() => setFocus(null)}
          >
            <i className="inline-block h-[3px] w-2.5 rounded-sm" style={{ background: colors[t.ticker] }} />
            {t.ticker}
          </span>
        ))}
      </div>
      {node}
    </div>
  )
}
