import { useState } from 'react'
import { useSectorMentions } from '../hooks/useSectorMentions'
import type { SectorMentionIndustry, SectorMentionItem, SectorMentionTicker } from '../types'

interface Props {
  windowHours?: number
  userFilter?: string | null
  subscriberOnly?: boolean
  onTickerClick?: (ticker: string) => void
}

function TickerChips({
  tickers,
  onTickerClick,
}: {
  tickers: SectorMentionTicker[]
  onTickerClick?: (ticker: string) => void
}) {
  return (
    <span className="flex flex-wrap gap-1">
      {tickers.map(t => (
        <button
          key={t.ticker}
          type="button"
          onClick={() => onTickerClick?.(t.ticker)}
          className="font-mono text-[10px] text-zinc-400 hover:text-zinc-100 bg-zinc-900 border border-zinc-800 rounded px-1.5 py-0.5"
        >
          <span>${t.ticker}</span>{' '}
          <span className="text-zinc-600">{t.mentions}</span>
        </button>
      ))}
    </span>
  )
}

function IndustryRow({
  industry,
  onTickerClick,
}: {
  industry: SectorMentionIndustry
  onTickerClick?: (ticker: string) => void
}) {
  return (
    <div className="flex flex-col gap-1 py-1.5 pl-5 border-b border-zinc-900 last:border-0">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] text-zinc-400 truncate">{industry.industry}</span>
        <span className="font-mono text-[10px] text-zinc-500 shrink-0">
          {industry.mentions} · {industry.unique_tickers} {industry.unique_tickers === 1 ? 'ticker' : 'tickers'}
        </span>
      </div>
      <TickerChips tickers={industry.top_tickers} onTickerClick={onTickerClick} />
    </div>
  )
}

function hasIndustryBreakdown(sector: SectorMentionItem): boolean {
  if (sector.industries.length > 1) return true
  return sector.industries.length === 1 && sector.industries[0].industry !== 'Other'
}

function SectorRow({
  sector,
  maxScore,
  onTickerClick,
}: {
  sector: SectorMentionItem
  maxScore: number
  onTickerClick?: (ticker: string) => void
}) {
  const [open, setOpen] = useState(false)
  const expandable = hasIndustryBreakdown(sector)
  const barWidth = `${Math.min(100, (sector.mention_score / maxScore) * 100).toFixed(1)}%`

  return (
    <div className="border-b border-zinc-900 last:border-0">
      <button
        type="button"
        onClick={() => expandable && setOpen(v => !v)}
        aria-expanded={expandable ? open : undefined}
        className={`flex w-full items-center gap-2 py-2 text-left ${expandable ? 'cursor-pointer' : 'cursor-default'}`}
      >
        <span className="w-3 shrink-0 text-center text-[10px] text-zinc-600">
          {expandable ? (open ? '▾' : '▸') : ''}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-[12px] font-semibold text-zinc-100">{sector.sector}</span>
            <span className="font-mono text-[10px] text-zinc-500 shrink-0">
              {sector.mentions} mentions · {sector.unique_tickers} {sector.unique_tickers === 1 ? 'ticker' : 'tickers'}
            </span>
          </div>
          <div className="mt-1 h-1.5 rounded-full bg-zinc-900">
            <div className="h-1.5 rounded-full bg-sky-500" style={{ width: barWidth }} />
          </div>
        </div>
      </button>
      {!open && (
        <div className="pb-2 pl-5">
          <TickerChips tickers={sector.top_tickers} onTickerClick={onTickerClick} />
        </div>
      )}
      {expandable && open && (
        <div className="pb-1.5">
          {sector.industries.map(industry => (
            <IndustryRow key={industry.industry} industry={industry} onTickerClick={onTickerClick} />
          ))}
        </div>
      )}
    </div>
  )
}

export function SectorMentionsWidget({
  windowHours = 24,
  userFilter = null,
  subscriberOnly = false,
  onTickerClick,
}: Props) {
  const { data, loading, error } = useSectorMentions(windowHours, userFilter, subscriberOnly)

  if (loading) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 flex flex-col gap-3">
        <div className="h-4 w-40 bg-zinc-800 rounded animate-pulse" />
        {[0, 1, 2, 3].map(i => (
          <div key={i} className="h-6 bg-zinc-800 rounded animate-pulse" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 text-zinc-500 text-sm">
        Failed to load sector mentions.
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 text-zinc-500 text-sm">
        No sector data yet — sector mentions need classified equity tickers.
      </div>
    )
  }

  const maxScore = Math.max(...data.map(s => s.mention_score)) || 1

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 flex flex-col gap-0">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-[13px] font-semibold text-zinc-100">Sectors &amp; industries</h2>
        <span className="text-[10px] text-zinc-500 font-mono">most mentioned · expand for detail</span>
      </div>
      <div className="flex flex-col">
        {data.map(sector => (
          <SectorRow key={sector.sector} sector={sector} maxScore={maxScore} onTickerClick={onTickerClick} />
        ))}
      </div>
    </div>
  )
}
