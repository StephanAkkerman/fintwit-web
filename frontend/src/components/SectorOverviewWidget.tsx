import { useState } from 'react'
import { useSectorOverview } from '../hooks/useSectorOverview'
import type { SectorPerformance, SectorSubsectorPerformance, SpyHeatmapDateRange } from '../types'

const RANGE_OPTIONS: Array<{ key: SpyHeatmapDateRange; label: string }> = [
  { key: 'one_day', label: '1D' },
  { key: 'one_week', label: '1W' },
  { key: 'one_month', label: '1M' },
  { key: 'ytd', label: 'YTD' },
  { key: 'one_year', label: '1Y' },
]

function formatMarketCap(value: number): string {
  if (value >= 1_000_000_000_000) return `$${(value / 1_000_000_000_000).toFixed(2)}T`
  if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  return `$${Math.round(value).toLocaleString()}`
}

function formatChange(changePercent: number | null): string {
  if (changePercent === null) return 'N/A'
  return `${changePercent >= 0 ? '+' : ''}${changePercent.toFixed(2)}%`
}

function changeColorClass(changePercent: number | null): string {
  if (changePercent === null) return 'text-zinc-500'
  if (changePercent > 0) return 'text-emerald-600 dark:text-emerald-400'
  if (changePercent < 0) return 'text-rose-600 dark:text-rose-400'
  return 'text-zinc-500'
}

function barColorClass(changePercent: number | null): string {
  if (changePercent === null) return 'bg-zinc-300 dark:bg-zinc-700'
  if (changePercent >= 2) return 'bg-emerald-500'
  if (changePercent > 0) return 'bg-emerald-400'
  if (changePercent <= -2) return 'bg-rose-500'
  if (changePercent < 0) return 'bg-rose-400'
  return 'bg-zinc-400'
}

// A bar of ±3% fills the row; wider moves just clip at 100%.
function barWidthPercent(changePercent: number | null): number {
  if (changePercent === null) return 0
  return Math.min(100, (Math.abs(changePercent) / 3) * 100)
}

function hasSubsectorBreakdown(sector: SectorPerformance): boolean {
  if (sector.subsectors.length > 1) return true
  return sector.subsectors.length === 1 && sector.subsectors[0].industry !== 'Other'
}

function SubsectorRow({ subsector }: { subsector: SectorSubsectorPerformance }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5 pl-6 pr-2 text-xs">
      <div className="min-w-0 truncate text-zinc-600 dark:text-zinc-400">
        {subsector.industry}
        <span className="ml-1.5 text-zinc-400 dark:text-zinc-600">
          {subsector.stock_count} {subsector.stock_count === 1 ? 'stock' : 'stocks'}
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <span className="text-zinc-500">{formatMarketCap(subsector.market_cap)}</span>
        <span className={`font-mono font-semibold ${changeColorClass(subsector.change_percent)}`}>
          {formatChange(subsector.change_percent)}
        </span>
      </div>
    </div>
  )
}

function SectorRow({ sector }: { sector: SectorPerformance }) {
  const expandable = hasSubsectorBreakdown(sector)
  const [open, setOpen] = useState(false)

  return (
    <div className="border-b border-zinc-100 last:border-0 dark:border-zinc-900">
      <button
        type="button"
        onClick={() => expandable && setOpen((v) => !v)}
        aria-expanded={expandable ? open : undefined}
        className={`flex w-full items-center gap-3 py-2 text-left ${
          expandable ? 'cursor-pointer' : 'cursor-default'
        }`}
      >
        <span className="w-4 shrink-0 text-center text-[10px] text-zinc-400">
          {expandable ? (open ? '▾' : '▸') : ''}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <span className="truncate text-sm font-medium text-zinc-800 dark:text-zinc-100">
              {sector.sector}
            </span>
            <div className="flex shrink-0 items-center gap-3 text-xs">
              <span className="text-zinc-500">{formatMarketCap(sector.market_cap)}</span>
              <span className="text-zinc-400">
                {sector.stock_count} {sector.stock_count === 1 ? 'stock' : 'stocks'}
              </span>
              <span className={`w-16 text-right font-mono font-semibold ${changeColorClass(sector.change_percent)}`}>
                {formatChange(sector.change_percent)}
              </span>
            </div>
          </div>
          <div className="mt-1 h-1.5 rounded-full bg-zinc-100 dark:bg-zinc-900">
            <div
              className={`h-1.5 rounded-full ${barColorClass(sector.change_percent)}`}
              style={{ width: `${barWidthPercent(sector.change_percent)}%` }}
            />
          </div>
        </div>
      </button>
      {expandable && open ? (
        <div className="pb-1.5">
          {sector.subsectors.map((subsector) => (
            <SubsectorRow key={subsector.industry} subsector={subsector} />
          ))}
        </div>
      ) : null}
    </div>
  )
}

export default function SectorOverviewWidget() {
  const [range, setRange] = useState<SpyHeatmapDateRange>('one_day')
  const { data, loading, error } = useSectorOverview(range)

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Sector Overview</h2>
          <p className="text-xs text-zinc-500">
            Market trends by sector — expand a sector for its subsector breakdown
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {RANGE_OPTIONS.map((option) => {
            const active = option.key === range
            return (
              <button
                key={option.key}
                type="button"
                onClick={() => setRange(option.key)}
                className={`rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                  active
                    ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                    : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
                }`}
              >
                {option.label}
              </button>
            )
          })}
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, idx) => (
            <div key={idx} className="h-8 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load sector overview data.</p>
      ) : data.length === 0 ? (
        <p className="text-sm text-zinc-500">No sector data available right now.</p>
      ) : (
        <div>
          {data.map((sector) => (
            <SectorRow key={sector.sector} sector={sector} />
          ))}
        </div>
      )}
    </div>
  )
}
