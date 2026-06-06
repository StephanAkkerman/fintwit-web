import { useMemo } from 'react'
import { useMentionHeat } from '../hooks/useMentionHeat'
import type { AssetKind, MentionHeatCell } from '../types'

export const MENTION_WINDOWS = [24, 48, 168] as const
export type MentionWindowHours = typeof MENTION_WINDOWS[number]

function windowLabel(h: MentionWindowHours): string {
  if (h < 48) return `${h}h`
  return `${h / 24}d`
}

interface LayoutItem {
  colStart: number
  rowStart: number
  size: number
}

// Gap-free heatmap layout using 6 columns (LCM of 1, 2, 3).
//
// Items are assigned sizes 1–3 based on mention share. Items are grouped by
// size (3 → 2 → 1). Within each group, only complete rows are placed
// (6/size items per row). Any leftover items that can't fill a complete row
// are demoted to the next smaller size and merged into that group, preserving
// relative mention-count order. This guarantees every row is fully packed
// with same-height tiles — no gaps, no orphans.
function computeLayout(
  data: MentionHeatCell[],
  maxItems = 20,
): { cells: MentionHeatCell[]; layouts: LayoutItem[] } {
  const COLS = 6
  const items = data.slice(0, maxItems)
  if (items.length === 0) return { cells: [], layouts: [] }

  const maxMentions = items[0].mentions
  type Sized = { cell: MentionHeatCell; size: number }

  const sized: Sized[] = items.map(d => ({
    cell: d,
    size: Math.max(1, Math.min(3, Math.round(Math.sqrt(d.mentions / maxMentions) * 3))),
  }))

  const result: Array<{ cell: MentionHeatCell; item: LayoutItem }> = []
  let curGridRow = 1

  function placeGroup(group: Sized[], size: number): Sized[] {
    if (size < 1 || group.length === 0) return []
    const perRow = Math.floor(COLS / size)
    const completeRows = Math.floor(group.length / perRow)
    // Size-1 tiles are the minimum; place all of them even if they don't fill a complete row.
    const toPlace = size === 1 ? group.length : completeRows * perRow

    for (let i = 0; i < toPlace; i++) {
      result.push({
        cell: group[i].cell,
        item: {
          colStart: (i % perRow) * size + 1,
          rowStart: curGridRow + Math.floor(i / perRow) * size,
          size,
        },
      })
    }
    curGridRow += completeRows * size
    return group.slice(toPlace).map(x => ({ ...x, size: size - 1 }))
  }

  const group3 = sized.filter(x => x.size === 3)
  const group2 = sized.filter(x => x.size === 2)
  const group1 = sized.filter(x => x.size === 1)

  const overflow3 = placeGroup(group3, 3)
  const merged2 = [...group2, ...overflow3].sort((a, b) => b.cell.mentions - a.cell.mentions)
  const overflow2 = placeGroup(merged2, 2)
  const merged1 = [...group1, ...overflow2].sort((a, b) => b.cell.mentions - a.cell.mentions)
  placeGroup(merged1, 1)

  return {
    cells: result.map(r => r.cell),
    layouts: result.map(r => r.item),
  }
}

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
  layout: LayoutItem
  onTickerClick?: (ticker: string) => void
}

function HeatCell({ cell, layout, onTickerClick }: CellProps) {
  const { colStart, rowStart, size } = layout

  const s = cell.avg_sentiment_24h ?? 0

  const tickerSize = size === 3 ? 'text-2xl' : size === 2 ? 'text-base' : 'text-[11px]'
  const pctSize    = size === 3 ? 'text-sm'  : 'text-[9px]'
  const cntSize    = size === 3 ? 'text-xs'  : 'text-[9px]'

  const pricePct = cell.price_direction != null
    ? (cell.price_direction > 0 ? '+' : '') + cell.price_direction.toFixed(1) + '%'
    : null

  return (
    <button
      onClick={() => onTickerClick?.(cell.ticker)}
      className="rounded-lg p-1.5 text-left flex flex-col justify-between hover:brightness-125 transition-[filter] focus:outline-none focus:ring-1 focus:ring-zinc-300"
      style={{
        gridColumn: `${colStart} / span ${size}`,
        gridRow: `${rowStart} / span ${size}`,
        background: sentimentBg(s),
        color: sentimentFg(s),
        border: `1.5px solid ${priceRingColor(cell.price_direction)}`,
      }}
    >
      <div>
        <span className={`font-mono font-bold tracking-tight ${tickerSize}`}>${cell.ticker}</span>
      </div>
      <div className="flex items-end justify-between gap-1">
        {size >= 2 && pricePct && (
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
  userFilter?: string | null
  subscriberOnly?: boolean
}

export function MentionHeatmap({
  assetKind,
  windowHours = MENTION_WINDOWS[0],
  onWindowChange,
  onTickerClick,
  height = 300,
  userFilter = null,
  subscriberOnly = false,
}: Props) {
  const { data, loading, error } = useMentionHeat(assetKind, windowHours, userFilter, subscriberOnly)

  const currentIdx = MENTION_WINDOWS.indexOf(windowHours)
  const canWiden   = onWindowChange != null && currentIdx < MENTION_WINDOWS.length - 1

  const sorted = useMemo(
    () => data.slice().sort((a, b) => b.mentions - a.mentions),
    [data]
  )
  const { cells, layouts } = useMemo(() => computeLayout(sorted, 20), [sorted])
  const rowHeight = Math.floor(height / 5)

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
          gridTemplateColumns: 'repeat(6, minmax(0,1fr))',
          gridAutoRows: `${rowHeight}px`,
        }}
      >
        {cells.map((cell, i) => (
          <HeatCell
            key={cell.ticker}
            cell={cell}
            layout={layouts[i]}
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
