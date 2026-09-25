import type { TrendTicker, TrendWindow } from '../../types'
import { useElementWidth } from '../../hooks/useElementWidth'
import { INK, fmtNet, formatBucket, netOf, sentimentColor } from '../../utils/trendSummary'
import { TipRow, TipTitle, useChartTooltip } from './ChartTooltip'

const ROWS = 10
const LABEL_W = 54
const NET_W = 56
const GAP = 2
const ROW_H = 22
const MIN_CELL = 12

interface Props {
  tickers: TrendTicker[]
  buckets: string[]
  window: TrendWindow
  onTickerClick?: (ticker: string) => void
}

export function SentimentTimeline({ tickers, buckets, window: win, onTickerClick }: Props) {
  const [ref, avail] = useElementWidth<HTMLDivElement>()
  const { show, hide, node } = useChartTooltip()
  const rows = tickers.slice(0, ROWS)
  const n = buckets.length

  if (rows.length === 0 || n === 0) {
    return <div ref={ref} className="py-8 text-center text-sm text-zinc-500">No ticker mentions in this window yet.</div>
  }

  // Cells shrink to fit; below MIN_CELL the chart scrolls sideways instead.
  const cell = Math.max(MIN_CELL, Math.floor((avail - LABEL_W - NET_W) / n) - GAP)
  const W = LABEL_W + n * (cell + GAP) + NET_W
  const H = rows.length * (ROW_H + GAP) + 22
  const maxM = Math.max(1, ...rows.flatMap(t => t.series.mentions))
  const ticks = [0, Math.floor((n - 1) / 3), Math.floor((2 * (n - 1)) / 3), n - 1]
  const gridEnd = LABEL_W + n * (cell + GAP) - GAP

  return (
    <div ref={ref} className="w-full">
      <div className="overflow-x-auto">
        <svg width={W} height={H} role="img" aria-label="Net sentiment per ticker per time slot" className="block">
          {rows.map((t, r) => {
            const y = r * (ROW_H + GAP)
            return (
              <g key={t.ticker}>
                <text
                  x={0} y={y + ROW_H / 2 + 4} fontSize={11} fontWeight={600} fill={INK.text}
                  className="cursor-pointer font-mono hover:fill-sky-300"
                  onClick={() => onTickerClick?.(t.ticker)}
                >
                  {t.ticker}
                </text>
                {t.series.mentions.map((mentions, i) => {
                  const bull = t.series.bull[i], bear = t.series.bear[i]
                  const net = netOf(bull, bear)
                  return (
                    <rect
                      key={i}
                      x={LABEL_W + i * (cell + GAP)} y={y} width={cell} height={ROW_H} rx={3}
                      fill={mentions ? sentimentColor(net) : INK.empty}
                      fillOpacity={mentions ? 0.25 + 0.75 * Math.sqrt(mentions / maxM) : 0.35}
                      onMouseMove={e => show(e, (
                        <>
                          <TipTitle>{t.ticker} · {formatBucket(buckets[i], win, true)}</TipTitle>
                          <TipRow label="mentions" value={mentions} />
                          <TipRow label="bullish" value={bull} />
                          <TipRow label="bearish" value={bear} />
                          <TipRow label="net" value={fmtNet(net)} />
                        </>
                      ))}
                      onMouseLeave={hide}
                    />
                  )
                })}
                <text
                  x={gridEnd + 10} y={y + ROW_H / 2 + 4} fontSize={11} className="font-mono"
                  fill={t.net_sentiment === null ? INK.muted : t.net_sentiment >= 0 ? INK.bull : INK.bear}
                >
                  {fmtNet(t.net_sentiment)}
                </text>
              </g>
            )
          })}
          {ticks.map(i => (
            <text
              key={i} fontSize={10} fill={INK.muted} className="font-mono" y={H - 4}
              x={i === 0 ? LABEL_W : i === n - 1 ? gridEnd : LABEL_W + i * (cell + GAP) + cell / 2}
              textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}
            >
              {i === n - 1 ? 'now' : formatBucket(buckets[i], win)}
            </text>
          ))}
          <text x={gridEnd + 10} y={H - 4} fontSize={10} fill={INK.muted} className="font-mono">net</text>
        </svg>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 font-mono text-[11px] text-zinc-400">
        <span className="inline-flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[3px]" style={{ background: INK.bear }} />bearish</span>
        <span className="inline-flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[3px]" style={{ background: INK.neutral }} />mixed</span>
        <span className="inline-flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 rounded-[3px]" style={{ background: INK.bull }} />bullish</span>
        <span className="text-zinc-500">fainter = fewer mentions</span>
      </div>
      {node}
    </div>
  )
}
