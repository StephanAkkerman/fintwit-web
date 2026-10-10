import { useEffect, useMemo, useState } from 'react'
import { useMentionHeat } from '../hooks/useMentionHeat'
import { squarify, type TreemapRect } from '../utils/treemap'
import type { AssetKind, MentionHeatCell } from '../types'

export const MENTION_WINDOWS = [24, 48, 168] as const
export type MentionWindowHours = typeof MENTION_WINDOWS[number]

function windowLabel(h: MentionWindowHours): string {
  if (h < 48) return `${h}h`
  return `${h / 24}d`
}

// Broad-market index trackers (issue #205). They are mentioned in nearly every
// macro tweet, so as treemap tiles they swallow the canvas without saying
// anything about which part of the market people are talking about. They get
// their own compact "Broad market" strip above the treemap instead.
export const BROAD_MARKET_TICKERS = new Set([
  'SPY', 'QQQ', 'IWM', 'DIA', 'VOO', 'VTI', 'IVV', 'SPX', 'NDX', 'RUT',
  'ES', 'NQ', 'RTY', 'YM', 'VIX', 'SPXL', 'TQQQ', 'SQQQ',
])

const MAX_TILES = 40
const GAP = 2
const HEADER_H = 18
const MIN_HEADER_W = 70
const MIN_HEADER_H = 40
const MIN_LABEL_W = 34
const MIN_LABEL_H = 20

// Fairness-adjusted weight (issue #191): the backend caps each author's
// contribution per ticker, so one account spamming $EUR can't dominate. Fall
// back to raw mentions for payloads without a score.
const weight = (c: MentionHeatCell): number => c.mention_score ?? c.mentions

type Industry = {
  name: string | null
  weight: number
  sentiment: number
  cells: MentionHeatCell[]
}

type Group = {
  name: string
  weight: number
  mentions: number
  sentiment: number
  industries: Industry[]
}

// Equities are grouped by their sector; everything without sector metadata
// falls back to a bucket named after its asset class.
function groupName(c: MentionHeatCell): string {
  const sector = c.sector?.trim()
  if (sector) return sector
  switch (c.asset_kind.toUpperCase()) {
    case 'CRYPTO':
    case 'CRYPTOCURRENCY':
      return 'Crypto'
    case 'FOREX':
      return 'Forex'
    case 'ETF':
    case 'INDEX':
    case 'MUTUALFUND':
      return 'ETFs & indexes'
    case 'FUTURE':
    case 'COMMODITY':
      return 'Futures & commodities'
    default:
      return 'Unclassified'
  }
}

// Mention-weighted average sentiment, so a group's color is the direction
// the conversation about it leans, not a mean dragged around by one-off tiles.
function weightedSentiment(cells: MentionHeatCell[]): number {
  let total = 0
  let sum = 0
  for (const c of cells) {
    const w = weight(c)
    total += w
    sum += (c.avg_sentiment_24h ?? 0) * w
  }
  return total ? sum / total : 0
}

export function buildGroups(cells: MentionHeatCell[]): Group[] {
  const groups = new Map<string, Map<string | null, MentionHeatCell[]>>()
  for (const c of cells) {
    const g = groupName(c)
    const industries = groups.get(g) ?? new Map<string | null, MentionHeatCell[]>()
    groups.set(g, industries)
    const ind = c.industry?.trim() || null
    const list = industries.get(ind) ?? []
    industries.set(ind, list)
    list.push(c)
  }

  const out: Group[] = []
  for (const [name, industryMap] of groups) {
    const industries: Industry[] = [...industryMap].map(([ind, list]) => ({
      name: ind,
      weight: list.reduce((s, c) => s + weight(c), 0),
      sentiment: weightedSentiment(list),
      cells: list.slice().sort((a, b) => weight(b) - weight(a)),
    }))
    industries.sort((a, b) => b.weight - a.weight)
    const all = industries.flatMap(i => i.cells)
    out.push({
      name,
      weight: industries.reduce((s, i) => s + i.weight, 0),
      mentions: all.reduce((s, c) => s + c.mentions, 0),
      sentiment: weightedSentiment(all),
      industries,
    })
  }
  out.sort((a, b) => b.weight - a.weight)
  return out
}

// A smooth red -> gray -> green ramp (same shape as the market heatmap), keyed
// on sentiment in [-1, 1]. Saturates at ±0.6, which is already a strong lean.
function sentimentColor(s: number): string {
  const clamped = Math.max(-0.6, Math.min(0.6, s))
  const intensity = Math.abs(clamped) / 0.6
  if (intensity < 0.08) return 'rgb(63, 63, 70)' // zinc-700, neutral
  const hue = clamped >= 0 ? 152 : 355
  const saturation = 30 + intensity * 45
  const lightness = 26 + intensity * 14
  return `hsl(${hue}deg ${saturation}% ${lightness}%)`
}

function sentimentLabel(s: number): string {
  if (s > 0.1) return 'Bullish'
  if (s < -0.1) return 'Bearish'
  return 'Neutral'
}

function priceRingColor(p: number | null): string {
  if (p === null) return 'rgba(0,0,0,0.25)'
  if (p >  0.5) return 'rgba(52,211,153,0.9)'
  if (p >  0)   return 'rgba(110,231,183,0.55)'
  if (p < -0.5) return 'rgba(244,63,94,0.9)'
  if (p <  0)   return 'rgba(253,164,175,0.55)'
  return 'rgba(0,0,0,0.25)'
}

function formatPct(p: number | null): string | null {
  if (p == null) return null
  return (p > 0 ? '+' : '') + p.toFixed(1) + '%'
}

function cellTitle(c: MentionHeatCell): string {
  const parts = [
    `$${c.ticker}`,
    `${c.mentions} mentions`,
    `${sentimentLabel(c.avg_sentiment_24h ?? 0).toLowerCase()} (${(c.avg_sentiment_24h ?? 0).toFixed(2)})`,
  ]
  const pct = formatPct(c.price_direction)
  if (pct) parts.push(`price ${pct}`)
  if (c.industry) parts.push(c.industry)
  return parts.join(' · ')
}

function TickerTile({
  rect,
  onTickerClick,
}: {
  rect: TreemapRect<MentionHeatCell>
  onTickerClick?: (ticker: string) => void
}) {
  const { data: cell, w, h } = rect
  const showLabel = w >= MIN_LABEL_W && h >= MIN_LABEL_H
  const big = w >= 110 && h >= 70
  const pct = formatPct(cell.price_direction)
  return (
    <button
      type="button"
      data-testid="mention-heat-tile"
      onClick={(e) => { e.stopPropagation(); onTickerClick?.(cell.ticker) }}
      title={cellTitle(cell)}
      className="absolute overflow-hidden rounded-[3px] text-left text-white hover:brightness-125 transition-[filter] focus:outline-none focus:ring-1 focus:ring-zinc-300"
      style={{
        left: `${rect.x}px`,
        top: `${rect.y}px`,
        width: `${Math.max(w - GAP, 0)}px`,
        height: `${Math.max(h - GAP, 0)}px`,
        background: sentimentColor(cell.avg_sentiment_24h ?? 0),
        border: `1.5px solid ${priceRingColor(cell.price_direction)}`,
      }}
    >
      {showLabel ? (
        <div className="flex h-full flex-col justify-center px-1.5 leading-tight">
          <span className={`truncate font-mono font-bold tracking-tight ${big ? 'text-lg' : 'text-[11px]'}`}>
            ${cell.ticker}
          </span>
          {h >= MIN_LABEL_H + 12 ? (
            <span className={`truncate font-mono opacity-80 ${big ? 'text-xs' : 'text-[9px]'}`}>
              {pct ? `${pct} · ` : ''}{cell.mentions}
            </span>
          ) : null}
        </div>
      ) : null}
    </button>
  )
}

function IndustryBlock({
  rect,
  onTickerClick,
}: {
  rect: TreemapRect<Industry>
  onTickerClick?: (ticker: string) => void
}) {
  const { data: industry, w, h } = rect
  // Single-ticker industries and asset classes without industries don't need
  // a header: the ticker tile already says everything.
  const showHeader =
    industry.name != null && industry.cells.length > 1 && w >= MIN_HEADER_W && h >= MIN_HEADER_H
  const headerH = showHeader ? HEADER_H : 0
  const tiles = useMemo(
    () => squarify(
      industry.cells.map(c => ({ value: weight(c), data: c })),
      0,
      headerH,
      w - GAP,
      h - headerH - GAP,
    ),
    [industry.cells, w, h, headerH],
  )
  return (
    <div
      className="absolute overflow-hidden rounded-md"
      style={{
        left: `${rect.x}px`,
        top: `${rect.y}px`,
        width: `${Math.max(w - GAP, 0)}px`,
        height: `${Math.max(h - GAP, 0)}px`,
        background: sentimentColor(industry.sentiment),
      }}
    >
      {showHeader ? (
        <div
          className="truncate bg-black/25 px-1.5 text-[10px] font-semibold text-white"
          style={{ height: `${HEADER_H}px`, lineHeight: `${HEADER_H}px` }}
          title={`${industry.name} · ${sentimentLabel(industry.sentiment).toLowerCase()}`}
        >
          {industry.name}
        </div>
      ) : null}
      {tiles.map(r => (
        <TickerTile key={r.data.ticker} rect={r} onTickerClick={onTickerClick} />
      ))}
    </div>
  )
}

function GroupBlock({
  rect,
  onSelect,
  onTickerClick,
}: {
  rect: TreemapRect<Group>
  onSelect: (name: string) => void
  onTickerClick?: (ticker: string) => void
}) {
  const { data: group, w, h } = rect
  const showHeader = w >= MIN_HEADER_W && h >= MIN_HEADER_H
  const headerH = showHeader ? HEADER_H + 2 : 0
  const industryRects = useMemo(
    () => squarify(
      group.industries.map(i => ({ value: i.weight, data: i })),
      0,
      headerH,
      w - GAP,
      h - headerH - GAP,
    ),
    [group.industries, w, h, headerH],
  )
  return (
    <div
      data-testid="mention-heat-group"
      className="absolute overflow-hidden rounded-lg border border-black/40 bg-zinc-950/40"
      style={{
        left: `${rect.x}px`,
        top: `${rect.y}px`,
        width: `${Math.max(w - GAP, 0)}px`,
        height: `${Math.max(h - GAP, 0)}px`,
      }}
    >
      {showHeader ? (
        <button
          type="button"
          onClick={() => onSelect(group.name)}
          aria-label={`Show ${group.name} in detail`}
          title={`${group.name} · ${sentimentLabel(group.sentiment).toLowerCase()} · ${group.mentions} mentions`}
          className="flex w-full items-center justify-between gap-2 px-2 text-[11px] font-bold uppercase tracking-wide text-white hover:brightness-125"
          style={{ height: `${HEADER_H + 2}px`, background: sentimentColor(group.sentiment) }}
        >
          <span className="truncate">{group.name}</span>
          {w >= 160 ? (
            <span className="shrink-0 font-mono text-[10px] font-semibold normal-case opacity-90">
              {sentimentLabel(group.sentiment)} · {group.mentions}
            </span>
          ) : null}
        </button>
      ) : null}
      {industryRects.map(r => (
        <IndustryBlock key={r.data.name ?? '_'} rect={r} onTickerClick={onTickerClick} />
      ))}
    </div>
  )
}

function BroadMarketStrip({
  cells,
  onTickerClick,
}: {
  cells: MentionHeatCell[]
  onTickerClick?: (ticker: string) => void
}) {
  return (
    <div data-testid="mention-heat-broad-market" className="mb-2 flex flex-wrap items-center gap-1.5">
      <span className="mr-1 text-[10px] uppercase tracking-wide text-zinc-500">Broad market</span>
      {cells.map(c => {
        const pct = formatPct(c.price_direction)
        return (
          <button
            key={c.ticker}
            type="button"
            onClick={() => onTickerClick?.(c.ticker)}
            title={cellTitle(c)}
            className="flex items-center gap-1.5 rounded-md px-2 py-0.5 font-mono text-[11px] text-white hover:brightness-125"
            style={{
              background: sentimentColor(c.avg_sentiment_24h ?? 0),
              border: `1.5px solid ${priceRingColor(c.price_direction)}`,
            }}
          >
            <span className="font-bold">${c.ticker}</span>
            {pct ? <span className="opacity-90">{pct}</span> : null}
            <span className="opacity-60">{c.mentions}</span>
          </button>
        )
      })}
    </div>
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
  height = 320,
  userFilter = null,
  subscriberOnly = false,
}: Props) {
  const { data, loading, error } = useMentionHeat(assetKind, windowHours, userFilter, subscriberOnly)
  // Callback ref: the canvas mounts and unmounts with loading/empty states,
  // so the observer has to follow whichever element is current.
  const [container, setContainer] = useState<HTMLDivElement | null>(null)
  const [width, setWidth] = useState(960)
  const [selected, setSelected] = useState<string | null>(null)

  const currentIdx = MENTION_WINDOWS.indexOf(windowHours)
  const canWiden   = onWindowChange != null && currentIdx < MENTION_WINDOWS.length - 1

  const { broad, groups } = useMemo(() => {
    const sorted = data.slice().sort((a, b) => weight(b) - weight(a))
    const broad = sorted.filter(c => BROAD_MARKET_TICKERS.has(c.ticker.toUpperCase()))
    const rest = sorted
      .filter(c => !BROAD_MARKET_TICKERS.has(c.ticker.toUpperCase()))
      .slice(0, MAX_TILES)
    return { broad, groups: buildGroups(rest) }
  }, [data])

  // Drop a drill-down whose group vanished (e.g. after a filter change).
  const selectedGroup = selected ? groups.find(g => g.name === selected) ?? null : null
  useEffect(() => {
    if (selected && !selectedGroup) setSelected(null)
  }, [selected, selectedGroup])

  const hasCanvas = groups.length > 0
  useEffect(() => {
    if (!container || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(entries => {
      const measured = entries[0]?.contentRect.width
      if (measured) setWidth(measured)
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [container])

  const groupRects = useMemo(
    () => squarify(
      (selectedGroup ? [selectedGroup] : groups).map(g => ({ value: g.weight, data: g })),
      0,
      0,
      width,
      height,
    ),
    [groups, selectedGroup, width, height],
  )

  if (loading) {
    return <div className="rounded-2xl border border-zinc-800 bg-zinc-900 h-[200px] animate-pulse" />
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900 h-[200px] flex items-center justify-center text-zinc-500 text-sm">
        Failed to load mention data.
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900 h-[200px] flex items-center justify-center text-zinc-500 text-sm">
        No tickers in the last {windowLabel(windowHours)}.{' '}
        {canWiden && (
          <button
            onClick={() => onWindowChange?.(MENTION_WINDOWS[currentIdx + 1])}
            className="ml-1 text-indigo-400 underline cursor-pointer hover:text-indigo-300"
          >
            widen window
          </button>
        )}
      </div>
    )
  }

  return (
    <div data-testid="mention-heatmap-container" className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-3">
        <h2 className="text-[13px] font-semibold text-zinc-100">Mention heat</h2>
        {selectedGroup ? (
          <nav aria-label="Mention heat drill-down" className="flex items-center gap-1 text-xs text-zinc-500">
            <button type="button" onClick={() => setSelected(null)} className="hover:underline">
              All
            </button>
            <span>/</span>
            <span className="font-semibold text-zinc-300">{selectedGroup.name}</span>
          </nav>
        ) : null}
        <span className="ml-auto text-[10px] text-zinc-500 font-mono">
          grouped by sector · sized by mentions (capped per account) · color by sentiment · ring by price Δ
        </span>
      </div>
      {broad.length > 0 ? <BroadMarketStrip cells={broad} onTickerClick={onTickerClick} /> : null}
      {hasCanvas ? (
        <div ref={setContainer} className="relative w-full" style={{ height: `${height}px` }}>
          {groupRects.map(r => (
            <GroupBlock key={r.data.name} rect={r} onSelect={setSelected} onTickerClick={onTickerClick} />
          ))}
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-3 text-[10px] text-zinc-500 font-mono">
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ background: sentimentColor(-0.6) }} />
          Bearish
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ background: sentimentColor(0) }} />
          Neutral
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ background: sentimentColor(0.6) }} />
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
