import { useMentionHeat } from '../hooks/useMentionHeat'
import type { AssetKind, MentionHeatCell } from '../types'

export const MENTION_WINDOWS = [24, 48, 168] as const
export type MentionWindowHours = typeof MENTION_WINDOWS[number]

function windowLabel(h: MentionWindowHours): string {
  if (h < 48) return `${h}h`
  return `${h / 24}d`
}

// Top-12 cell grid spans (8 cols × 5 rows = 40 cells total)
const HEAT_LAYOUT: Array<{ col: string; row: string }> = [
  { col: 'span 4', row: 'span 4' }, // rank 1: 16 cells
  { col: 'span 4', row: 'span 2' }, // rank 2:  8 cells
  { col: 'span 2', row: 'span 2' }, // rank 3:  4 cells
  { col: 'span 2', row: 'span 2' }, // rank 4:  4 cells
  { col: 'span 1', row: 'span 1' }, // ranks 5–12: 1 cell each
  { col: 'span 1', row: 'span 1' },
  { col: 'span 1', row: 'span 1' },
  { col: 'span 1', row: 'span 1' },
  { col: 'span 1', row: 'span 1' },
  { col: 'span 1', row: 'span 1' },
  { col: 'span 1', row: 'span 1' },
  { col: 'span 1', row: 'span 1' },
]

function sentimentBg(s: number): string {
  if (s <= -0.5) return 'rgba(225,29,72,0.55)'
  if (s <= -0.2) return 'rgba(244,63,94,0.32)'
  if (s <= -0.05) return 'rgba(251,113,133,0.18)'
  if (s <   0.05) return 'rgba(63,63,70,0.55)'
  if (s <   0.2)  return 'rgba(110,231,183,0.18)'
  if (s <   0.5)  return 'rgba(16,185,129,0.32)'
  return 'rgba(5,150,105,0.55)'
}

function sentimentFg(s: number): string {
  if (s <= -0.3) return '#fecdd3'
  if (s <= -0.05) return '#fda4af'
  if (s <   0.05) return '#e4e4e7'
  if (s <   0.3)  return '#a7f3d0'
  return '#d1fae5'
}

function priceRingColor(p: number | null): string {
  if (p === null) return 'rgba(82,82,91,0.5)'
  if (p >  0.5) return 'rgba(52,211,153,0.7)'
  if (p >  0)   return 'rgba(110,231,183,0.4)'
  if (p < -0.5) return 'rgba(244,63,94,0.7)'
  if (p <  0)   return 'rgba(253,164,175,0.4)'
  return 'rgba(82,82,91,0.5)'
}

interface CellProps {
  cell: MentionHeatCell
  rank: number
  rowHeight: number
  onTickerClick?: (ticker: string) => void
}

function HeatCell({ cell, rank, rowHeight, onTickerClick }: CellProps) {
  const layout = HEAT_LAYOUT[rank] ?? { col: 'span 1', row: 'span 1' }
  const isHuge = rank === 0
  const isBig  = rank < 4
  const s = cell.avg_sentiment_24h ?? 0

  const tickerSize = isHuge ? 'text-3xl' : isBig ? 'text-xl' : 'text-[11px]'
  const pctSize    = isHuge ? 'text-sm'  : isBig ? 'text-[10px]' : 'text-[9px]'
  const cntSize    = isHuge ? 'text-xs'  : isBig ? 'text-[10px]' : 'text-[9px]'

  const pricePct = cell.price_direction != null
    ? (cell.price_direction > 0 ? '+' : '') + cell.price_direction.toFixed(1) + '%'
    : null

  return (
    <button
      onClick={() => onTickerClick?.(cell.ticker)}
      className="rounded-lg p-1.5 text-left flex flex-col justify-between hover:brightness-125 transition-[filter] focus:outline-none focus:ring-1 focus:ring-zinc-300"
      style={{
        gridColumn: layout.col,
        gridRow: layout.row,
        background: sentimentBg(s),
        color: sentimentFg(s),
        border: `1.5px solid ${priceRingColor(cell.price_direction)}`,
      }}
    >
      <div>
        <span className={`font-mono font-bold tracking-tight ${tickerSize}`}>${cell.ticker}</span>
        {isHuge && (
          <div className="font-mono text-[10px] opacity-60 truncate mt-0.5">{cell.ticker}</div>
        )}
      </div>
      <div className="flex items-end justify-between gap-1">
        {isBig && pricePct && (
          <span className={`font-mono font-semibold ${pctSize}`}>{pricePct}</span>
        )}
        <span className={`font-mono opacity-60 ml-auto ${cntSize}`}>{cell.mentions}</span>
      </div>
    </button>
  )
}

interface Props {
  assetKind: AssetKind
  windowHours?: MentionWindowHours
  onWindowChange?: (next: MentionWindowHours) => void
  onTickerClick?: (ticker: string) => void
  height?: number
}

export function MentionHeatmap({
  assetKind,
  windowHours = MENTION_WINDOWS[0],
  onWindowChange,
  onTickerClick,
  height = 300,
}: Props) {
  const { data, loading, error } = useMentionHeat(assetKind, windowHours)

  const currentIdx = MENTION_WINDOWS.indexOf(windowHours)
  const canWiden   = onWindowChange != null && currentIdx < MENTION_WINDOWS.length - 1

  if (loading) {
    return <div className="rounded-xl border border-zinc-800 bg-zinc-950 h-[200px] animate-pulse" />
  }

  if (error) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-950 h-[200px] flex items-center justify-center text-zinc-500 text-sm">
        Failed to load mention data.
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-950 h-[200px] flex items-center justify-center text-zinc-500 text-sm">
        No tickers in the last {windowLabel(windowHours)}.{' '}
        {canWiden && (
          <button
            onClick={() => onWindowChange?.(MENTION_WINDOWS[currentIdx + 1])}
            className="ml-1 text-blue-400 underline cursor-pointer hover:text-blue-300"
          >
            widen window
          </button>
        )}
      </div>
    )
  }

  const top12 = data.slice().sort((a, b) => b.mentions - a.mentions).slice(0, 12)
  const rowHeight = Math.floor(height / 5)

  return (
    <div data-testid="mention-heatmap-container" className="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
      <div className="flex items-center mb-3">
        <h2 className="text-[13px] font-semibold text-zinc-100">Mention heat</h2>
        <span className="ml-auto text-[10px] text-zinc-500 font-mono">
          sized by mentions · color by sentiment · ring by price Δ
        </span>
      </div>
      <div
        className="grid gap-1.5"
        style={{
          gridTemplateColumns: 'repeat(8, minmax(0,1fr))',
          gridTemplateRows: `repeat(5, ${rowHeight}px)`,
        }}
      >
        {top12.map((cell, i) => (
          <HeatCell
            key={cell.ticker}
            cell={cell}
            rank={i}
            rowHeight={rowHeight}
            onTickerClick={onTickerClick}
          />
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3 text-[10px] text-zinc-500 font-mono">
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ background: sentimentBg(-0.6) }} />
          Bearish
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ background: sentimentBg(0) }} />
          Neutral
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ background: sentimentBg(0.6) }} />
          Bullish
        </span>
        <span className="ml-3 flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-sm inline-block border-[1.5px]" style={{ borderColor: priceRingColor(1) }} />
          Price up
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-sm inline-block border-[1.5px]" style={{ borderColor: priceRingColor(-1) }} />
          Price down
        </span>
      </div>
    </div>
  )
}
