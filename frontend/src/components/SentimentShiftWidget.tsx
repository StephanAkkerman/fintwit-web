import type { AssetKind, SentimentShiftItem } from '../types'
import { useSentimentShift } from '../hooks/useSentimentShift'

interface Props {
  assetKind: AssetKind
  windowHours?: number
}

function deltaTone(delta: number): { color: string; arrow: string } {
  if (delta >  0.02) return { color: 'text-emerald-400', arrow: '▲' }
  if (delta < -0.02) return { color: 'text-rose-400',    arrow: '▼' }
  return { color: 'text-zinc-400', arrow: '·' }
}

function formatSentiment(v: number): string {
  return (v >= 0 ? '+' : '') + v.toFixed(2)
}

// Maps a sentiment score (-1..1) to an SVG y coord in a 22-height canvas.
// Positive sentiment = top (y small), negative = bottom (y large).
function sentToY(s: number): number {
  return Math.max(1, Math.min(21, 11 - s * 10))
}

function ShiftSparkline({ prev, current }: { prev: number; current: number }) {
  const up = current >= prev
  const stroke = up ? '#34d399' : '#fb7185'
  const fill   = up ? 'rgba(52,211,153,0.10)' : 'rgba(244,63,94,0.10)'
  const y1 = sentToY(prev)
  const y2 = sentToY(current)
  return (
    <svg width="100%" height="22" viewBox="0 0 120 22" preserveAspectRatio="none" className="block">
      <path
        d={`M0,${y1.toFixed(1)} L120,${y2.toFixed(1)} L120,22 L0,22 Z`}
        fill={fill}
      />
      <path
        d={`M0,${y1.toFixed(1)} L120,${y2.toFixed(1)}`}
        fill="none" stroke={stroke} strokeWidth="1.5" strokeLinecap="round"
      />
      <circle cx="120" cy={y2.toFixed(1)} r="2" fill={stroke} />
    </svg>
  )
}

function Row({ item }: { item: SentimentShiftItem }) {
  const { color, arrow } = deltaTone(item.delta)
  return (
    <div className="grid items-center gap-2 py-1.5 border-b border-zinc-900 last:border-b-0"
      style={{ gridTemplateColumns: '60px 1fr 72px 56px' }}>
      <span className="font-mono text-[11px] text-zinc-100 font-semibold">{item.ticker}</span>
      <ShiftSparkline prev={item.avg_sentiment_prev} current={item.avg_sentiment_24h} />
      <span className="font-mono text-[10px] text-zinc-500 text-right whitespace-nowrap">
        {formatSentiment(item.avg_sentiment_prev)}
        {' → '}
        <span className="text-zinc-200">{formatSentiment(item.avg_sentiment_24h)}</span>
      </span>
      <span className={`font-mono text-[11px] font-bold text-right tabular-nums ${color}`}>
        {arrow} {Math.abs(item.delta) >= 0.02 ? `+${item.delta.toFixed(2)}` : '·'}
      </span>
    </div>
  )
}

export function SentimentShiftWidget({ assetKind, windowHours = 24 }: Props) {
  const { data, loading, error } = useSentimentShift(assetKind, windowHours)

  if (loading) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 flex flex-col gap-3">
        <div className="h-4 w-32 bg-zinc-800 rounded animate-pulse" />
        {[0, 1, 2].map(i => (
          <div key={i} className="h-5 bg-zinc-800 rounded animate-pulse" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 text-zinc-500 text-sm">
        Failed to load sentiment data.
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 text-zinc-500 text-sm">
        No sentiment shift data.
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 flex flex-col gap-0">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-[13px] font-semibold text-zinc-100">Sentiment Shift</h2>
        <span className="text-[10px] text-zinc-500 font-mono">biggest swings</span>
      </div>
      <div className="flex flex-col">
        {data.map(item => <Row key={item.ticker} item={item} />)}
      </div>
    </div>
  )
}
