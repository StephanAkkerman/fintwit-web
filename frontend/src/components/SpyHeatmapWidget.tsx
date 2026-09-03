import { useEffect, useMemo, useRef, useState } from 'react'
import { useSpyHeatmap } from '../hooks/useSpyHeatmap'
import { squarify, type TreemapRect } from '../utils/treemap'
import type { SpyHeatmapDateRange, SpyHeatmapItem } from '../types'

const RANGE_OPTIONS: Array<{ key: SpyHeatmapDateRange; label: string }> = [
  { key: 'one_day', label: '1D' },
  { key: 'one_week', label: '1W' },
  { key: 'one_month', label: '1M' },
  { key: 'ytd', label: 'YTD' },
  { key: 'one_year', label: '1Y' },
]

const CANVAS_HEIGHT = 560
const GAP = 2
// Below this, a box only gets a color -- text would overflow or be unreadable.
const MIN_LABEL_W = 40
const MIN_LABEL_H = 22
const MIN_HEADER_W = 60
const MIN_HEADER_H = 32
const HEADER_H = 20

type Ticker = {
  ticker: string
  changePercent: number | null
  marketCap: number
}

type Industry = {
  name: string
  marketCap: number
  changePercent: number | null
  tickers: Ticker[]
}

type Sector = {
  name: string
  marketCap: number
  changePercent: number | null
  industries: Industry[]
}

function toNumber(value: string | number | null | undefined): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

export function formatMarketCap(value: number): string {
  if (value >= 1_000_000_000_000) return `$${(value / 1_000_000_000_000).toFixed(2)}T`
  if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`
  return `$${Math.round(value).toLocaleString()}`
}

function formatChange(changePercent: number | null): string {
  if (changePercent === null) return 'N/A'
  return `${changePercent >= 0 ? '+' : ''}${changePercent.toFixed(2)}%`
}

// A smooth red -> gray -> green ramp instead of a handful of discrete
// buckets, so the overall market shape reads the same way it does on
// unusualwhales' heatmap.
function heatColor(changePercent: number | null): string {
  if (changePercent === null) return 'rgb(63, 63, 70)' // zinc-700
  const clamped = Math.max(-3, Math.min(3, changePercent))
  const intensity = Math.abs(clamped) / 3 // 0..1
  const lightness = 28 + intensity * 14 // 28%..42%
  const hue = clamped >= 0 ? 152 : 355
  const saturation = 35 + intensity * 40
  return `hsl(${hue}deg ${saturation}% ${lightness}%)`
}

function textToneClass(changePercent: number | null): string {
  if (changePercent === null) return 'text-zinc-300'
  return 'text-white'
}

function buildTree(data: SpyHeatmapItem[]): Sector[] {
  type Accum = { marketCap: number; weighted: number; industries: Map<string, { marketCap: number; weighted: number; tickers: Ticker[] }> }
  const sectors = new Map<string, Accum>()

  for (const row of data) {
    if (!row.ticker) continue
    const sectorName = (row.sector ?? '').trim() || 'Unknown'
    const industryName = (row.industry ?? '').trim() || 'Other'
    const marketCap = toNumber(row.marketcap) ?? 0
    const close = toNumber(row.close)
    const prevClose = toNumber(row.prev_close)
    const changePercent = close !== null && prevClose ? ((close - prevClose) / prevClose) * 100 : null

    const sector = sectors.get(sectorName) ?? { marketCap: 0, weighted: 0, industries: new Map() }
    sectors.set(sectorName, sector)
    sector.marketCap += marketCap
    if (changePercent !== null) sector.weighted += changePercent * marketCap

    const industry = sector.industries.get(industryName) ?? { marketCap: 0, weighted: 0, tickers: [] }
    sector.industries.set(industryName, industry)
    industry.marketCap += marketCap
    if (changePercent !== null) industry.weighted += changePercent * marketCap
    industry.tickers.push({ ticker: row.ticker, changePercent, marketCap })
  }

  const result: Sector[] = []
  for (const [name, sector] of sectors) {
    const industries: Industry[] = []
    for (const [industryName, industry] of sector.industries) {
      industries.push({
        name: industryName,
        marketCap: industry.marketCap,
        changePercent: industry.marketCap ? industry.weighted / industry.marketCap : null,
        tickers: industry.tickers.sort((a, b) => b.marketCap - a.marketCap),
      })
    }
    industries.sort((a, b) => b.marketCap - a.marketCap)
    result.push({
      name,
      marketCap: sector.marketCap,
      changePercent: sector.marketCap ? sector.weighted / sector.marketCap : null,
      industries,
    })
  }
  result.sort((a, b) => b.marketCap - a.marketCap)
  return result
}

type Crumb = { label: string; sector: string | null; industry: string | null }

function TickerCell({ rect }: { rect: TreemapRect<Ticker> }) {
  const { data: ticker, w, h } = rect
  const showLabel = w >= MIN_LABEL_W && h >= MIN_LABEL_H
  return (
    <div
      className="absolute overflow-hidden rounded-[3px] border border-black/20"
      style={{
        left: `${rect.x}px`,
        top: `${rect.y}px`,
        width: `${Math.max(rect.w - GAP, 0)}px`,
        height: `${Math.max(rect.h - GAP, 0)}px`,
        backgroundColor: heatColor(ticker.changePercent),
      }}
      title={`${ticker.ticker} · ${formatChange(ticker.changePercent)} · ${formatMarketCap(ticker.marketCap)}`}
    >
      {showLabel ? (
        <div className={`flex h-full flex-col justify-center px-1.5 leading-tight ${textToneClass(ticker.changePercent)}`}>
          <span className="truncate text-[11px] font-bold">{ticker.ticker}</span>
          {h >= MIN_LABEL_H + 12 ? (
            <span className="truncate text-[10px] font-mono opacity-90">{formatChange(ticker.changePercent)}</span>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function IndustryBlock({
  rect,
  onSelect,
}: {
  rect: TreemapRect<Industry>
  onSelect: (industryName: string) => void
}) {
  const { data: industry, w, h } = rect
  const showHeader = w >= MIN_HEADER_W && h >= MIN_HEADER_H
  const headerH = showHeader ? HEADER_H : 0
  const tickerRects = useMemo(() => {
    if (h - headerH <= 0 || w <= 0) return []
    return squarify(
      industry.tickers.map((t) => ({ value: t.marketCap, data: t })),
      0,
      headerH,
      w - GAP,
      h - headerH - GAP,
    )
  }, [industry.tickers, w, h, headerH])

  return (
    <div
      role={showHeader ? 'button' : undefined}
      tabIndex={showHeader ? 0 : undefined}
      onClick={showHeader ? (e) => { e.stopPropagation(); onSelect(industry.name) } : undefined}
      onKeyDown={
        showHeader
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.stopPropagation()
                onSelect(industry.name)
              }
            }
          : undefined
      }
      className={`absolute overflow-hidden rounded-md border border-black/30 ${showHeader ? 'cursor-pointer' : ''}`}
      style={{
        left: `${rect.x}px`,
        top: `${rect.y}px`,
        width: `${Math.max(rect.w - GAP, 0)}px`,
        height: `${Math.max(rect.h - GAP, 0)}px`,
        backgroundColor: heatColor(industry.changePercent),
      }}
      aria-label={showHeader ? `Show ${industry.name} in detail` : undefined}
    >
      {showHeader ? (
        <div className="flex items-center justify-between gap-2 bg-black/25 px-1.5 text-[11px] font-semibold text-white" style={{ height: `${HEADER_H}px` }}>
          <span className="truncate">{industry.name}</span>
          <span className="font-mono opacity-90">{formatChange(industry.changePercent)}</span>
        </div>
      ) : null}
      {tickerRects.map((r) => (
        <TickerCell key={r.data.ticker} rect={r} />
      ))}
    </div>
  )
}

function SectorBlock({
  rect,
  onSelectSector,
  onSelectIndustry,
}: {
  rect: TreemapRect<Sector>
  onSelectSector: (sectorName: string) => void
  onSelectIndustry: (sectorName: string, industryName: string) => void
}) {
  const { data: sector, w, h } = rect
  const showHeader = w >= MIN_HEADER_W && h >= MIN_HEADER_H
  const headerH = showHeader ? HEADER_H : 0
  const industryRects = useMemo(() => {
    if (h - headerH <= 0 || w <= 0) return []
    return squarify(
      sector.industries.map((ind) => ({ value: ind.marketCap, data: ind })),
      0,
      headerH,
      w - GAP,
      h - headerH - GAP,
    )
  }, [sector.industries, w, h, headerH])

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelectSector(sector.name)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onSelectSector(sector.name)
      }}
      className="absolute cursor-pointer overflow-hidden rounded-lg border border-black/40 bg-zinc-950/40"
      style={{
        left: `${rect.x}px`,
        top: `${rect.y}px`,
        width: `${Math.max(rect.w - GAP, 0)}px`,
        height: `${Math.max(rect.h - GAP, 0)}px`,
      }}
      aria-label={`Show ${sector.name} sector in detail`}
    >
      {showHeader ? (
        <div className="flex items-center justify-between gap-2 bg-black/50 px-2 text-xs font-bold uppercase tracking-wide text-white" style={{ height: `${HEADER_H}px` }}>
          <span className="truncate">{sector.name}</span>
          <span className="font-mono opacity-90">{formatChange(sector.changePercent)}</span>
        </div>
      ) : null}
      {industryRects.map((r) => (
        <IndustryBlock
          key={r.data.name}
          rect={r}
          onSelect={(industryName) => onSelectIndustry(sector.name, industryName)}
        />
      ))}
    </div>
  )
}

export default function SpyHeatmapWidget() {
  const [range, setRange] = useState<SpyHeatmapDateRange>('one_day')
  const [crumb, setCrumb] = useState<Crumb>({ label: 'Market', sector: null, industry: null })
  const { data, loading, error } = useSpyHeatmap(range)
  const containerRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(960)

  useEffect(() => {
    const el = containerRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) => {
      const measured = entries[0]?.contentRect.width
      if (measured) setWidth(measured)
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const sectors = useMemo(() => buildTree(data), [data])

  // Reset drill-down whenever the underlying sector/industry disappears
  // (e.g. after a range change) so we never render a stale, empty detail view.
  useEffect(() => {
    if (crumb.sector && !sectors.some((s) => s.name === crumb.sector)) {
      setCrumb({ label: 'Market', sector: null, industry: null })
    }
  }, [sectors, crumb.sector])

  const goToMarket = () => setCrumb({ label: 'Market', sector: null, industry: null })
  const goToSector = (sectorName: string) => setCrumb({ label: sectorName, sector: sectorName, industry: null })
  const goToIndustry = (sectorName: string, industryName: string) =>
    setCrumb({ label: industryName, sector: sectorName, industry: industryName })

  const selectedSector = crumb.sector ? sectors.find((s) => s.name === crumb.sector) ?? null : null
  const selectedIndustry = selectedSector && crumb.industry
    ? selectedSector.industries.find((i) => i.name === crumb.industry) ?? null
    : null

  const content = useMemo(() => {
    if (width <= 0) return null

    if (selectedIndustry) {
      const rects = squarify(
        selectedIndustry.tickers.map((t) => ({ value: t.marketCap, data: t })),
        0,
        0,
        width,
        CANVAS_HEIGHT,
      )
      return (
        <>
          {rects.map((r) => (
            <TickerCell key={r.data.ticker} rect={r} />
          ))}
        </>
      )
    }

    if (selectedSector) {
      const rects = squarify(
        selectedSector.industries.map((ind) => ({ value: ind.marketCap, data: ind })),
        0,
        0,
        width,
        CANVAS_HEIGHT,
      )
      return (
        <>
          {rects.map((r) => (
            <IndustryBlock key={r.data.name} rect={r} onSelect={(industryName) => goToIndustry(selectedSector.name, industryName)} />
          ))}
        </>
      )
    }

    const rects = squarify(
      sectors.map((s) => ({ value: s.marketCap, data: s })),
      0,
      0,
      width,
      CANVAS_HEIGHT,
    )
    return (
      <>
        {rects.map((r) => (
          <SectorBlock key={r.data.name} rect={r} onSelectSector={goToSector} onSelectIndustry={goToIndustry} />
        ))}
      </>
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectors, selectedSector, selectedIndustry, width])

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Market Heatmap</h2>
          <nav aria-label="Heatmap drill-down" className="flex items-center gap-1 text-xs text-zinc-500">
            <button
              type="button"
              onClick={goToMarket}
              className={crumb.sector ? 'hover:underline' : 'font-semibold text-zinc-700 dark:text-zinc-300'}
            >
              Market
            </button>
            {crumb.sector ? (
              <>
                <span>/</span>
                <button
                  type="button"
                  onClick={() => goToSector(crumb.sector as string)}
                  className={crumb.industry ? 'hover:underline' : 'font-semibold text-zinc-700 dark:text-zinc-300'}
                >
                  {crumb.sector}
                </button>
              </>
            ) : null}
            {crumb.industry ? (
              <>
                <span>/</span>
                <span className="font-semibold text-zinc-700 dark:text-zinc-300">{crumb.industry}</span>
              </>
            ) : null}
          </nav>
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
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6" style={{ height: `${CANVAS_HEIGHT}px` }}>
          {Array.from({ length: 24 }).map((_, idx) => (
            <div key={idx} className="animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load market heatmap data.</p>
      ) : sectors.length === 0 ? (
        <p className="text-sm text-zinc-500">No heatmap data available right now.</p>
      ) : (
        <div ref={containerRef} className="relative w-full" style={{ height: `${CANVAS_HEIGHT}px` }}>
          {content}
        </div>
      )}
    </div>
  )
}
