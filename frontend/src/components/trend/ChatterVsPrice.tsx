import type { TrendTicker, TrendWindow } from '../../types'
import { useElementWidth } from '../../hooks/useElementWidth'
import {
  INK, fmtCount, fmtGrowth, fmtPct, fmtPrice, formatBucket, growth, netOf, priceChange, sentimentColor,
} from '../../utils/trendSummary'
import { TipRow, TipTitle, useChartTooltip } from './ChartTooltip'

const SHOWN = 8
const PRICE_H = 38
const BAR_H = 34
const GAP = 6

interface CardProps {
  t: TrendTicker
  buckets: string[]
  window: TrendWindow
  onTickerClick?: (ticker: string) => void
}

function Multiple({ t, buckets, window: win, onTickerClick }: CardProps) {
  const [ref, w] = useElementWidth<HTMLDivElement>(220)
  const { show, hide, node } = useChartTooltip()
  const pc = priceChange(t)
  const n = t.series.mentions.length
  const H = PRICE_H + GAP + BAR_H

  // Price is drawn through the buckets that quoted one; empty buckets are skipped, not zeroed.
  const priced = t.series.price
    .map((p, i) => (p !== null && p > 0 ? { i, p } : null))
    .filter((v): v is { i: number; p: number } => v !== null)
  const lo = Math.min(...priced.map(v => v.p)), hi = Math.max(...priced.map(v => v.p))
  const X = (i: number) => (n > 1 ? (i / (n - 1)) * (w - 4) + 2 : w / 2)
  const Yp = (v: number) => PRICE_H - 3 - ((v - lo) / (hi - lo || 1)) * (PRICE_H - 6)
  const maxM = Math.max(1, ...t.series.mentions)
  const bw = Math.max(1.5, w / n - 2)
  const lastPriced = priced[priced.length - 1]

  return (
    // The whole card opens the ticker on click; the name is the keyboard target.
    <div
      onClick={() => onTickerClick?.(t.ticker)}
      className="min-w-0 cursor-pointer rounded-xl border border-transparent bg-zinc-950/40 px-3 py-2.5 hover:border-zinc-800"
    >
      <div className="flex items-baseline justify-between gap-1.5">
        <button
          type="button"
          onClick={e => { e.stopPropagation(); onTickerClick?.(t.ticker) }}
          className="rounded font-mono text-[13px] font-semibold text-zinc-100 hover:text-sky-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400"
        >
          {t.ticker}
        </button>
        {pc
          ? <span className={`font-mono text-[11px] ${pc.change >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{fmtPct(pc.change)}</span>
          : <span className="font-mono text-[11px] text-zinc-500">no price</span>}
      </div>
      <div className="mt-px truncate font-mono text-[10px] text-zinc-500">
        {pc ? `${fmtPrice(pc.last)} · ` : ''}{fmtCount(t.mentions)} mentions · {fmtGrowth(growth(t))}
      </div>
      <div ref={ref} className="mt-1.5">
        <svg
          width={w} height={H} role="img" aria-label={`${t.ticker} price and mentions`} className="block overflow-visible"
          onMouseMove={e => {
            const rect = e.currentTarget.getBoundingClientRect()
            const i = Math.min(n - 1, Math.max(0, Math.floor(((e.clientX - rect.left) / rect.width) * n)))
            const bull = t.series.bull[i], bear = t.series.bear[i], price = t.series.price[i]
            show(e, (
              <>
                <TipTitle>{t.ticker} · {formatBucket(buckets[i], win, true)}</TipTitle>
                <TipRow label="price" value={price !== null ? fmtPrice(price) : '–'} />
                <TipRow label="mentions" value={t.series.mentions[i]} />
                <TipRow label="bull / bear" value={`${bull} / ${bear}`} />
              </>
            ))
          }}
          onMouseLeave={hide}
        >
          {priced.length >= 2 && (
            <>
              <polyline
                points={priced.map(v => `${X(v.i)},${Yp(v.p)}`).join(' ')}
                fill="none" stroke="#a1a1aa" strokeWidth={1.5} strokeLinejoin="round"
              />
              <circle cx={X(lastPriced.i)} cy={Yp(lastPriced.p)} r={2.75} fill={pc && pc.change >= 0 ? INK.bull : INK.bear} />
            </>
          )}
          {t.series.mentions.map((mentions, i) => {
            const bh = mentions ? Math.max(1, (mentions / maxM) * BAR_H) : 0
            return bh > 0 && (
              <rect
                key={i}
                x={(i / n) * w + 1} y={PRICE_H + GAP + BAR_H - bh} width={bw} height={bh} rx={Math.min(2, bw / 2)}
                fill={sentimentColor(netOf(t.series.bull[i], t.series.bear[i]))}
              />
            )
          })}
        </svg>
      </div>
      {node}
    </div>
  )
}

interface Props {
  tickers: TrendTicker[]
  buckets: string[]
  window: TrendWindow
  onTickerClick?: (ticker: string) => void
}

export function ChatterVsPrice({ tickers, buckets, window, onTickerClick }: Props) {
  const shown = tickers.slice(0, SHOWN)
  if (shown.length === 0) {
    return <p className="py-8 text-center text-sm text-zinc-500">No ticker mentions in this window yet.</p>
  }
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {shown.map(t => (
        <Multiple key={t.ticker} t={t} buckets={buckets} window={window} onTickerClick={onTickerClick} />
      ))}
    </div>
  )
}
