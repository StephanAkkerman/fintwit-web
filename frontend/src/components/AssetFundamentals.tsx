import type { Asset } from '../types'
import type { MetricQuality, MetricScale } from '../utils/metricQuality'
import { metricQualityTextClass, scoreMetric } from '../utils/metricQuality'

/**
 * Conventional generic P/E bands: cheap at or under 15x earnings, expensive at
 * or over 30x. Deliberately sector-blind -- a high-growth name can read
 * "expensive" without being a bad company -- so the colour is a valuation cue,
 * not a verdict on the business.
 */
const PE_SCALE: MetricScale = { good: 15, bad: 30 }

const TOOLTIPS = {
  marketCap: 'Market cap — share price × shares outstanding. The total value the market puts on the company.',
  forwardPE:
    'Forward P/E — share price ÷ forecast earnings per share for the next 12 months. Lower means you pay less per unit of expected profit; it is omitted when analysts do not forecast a profit. Green at or under 15x, red at or over 30x — a valuation cue only, and not adjusted for sector or growth.',
  trailingPE:
    'P/E (TTM) — share price ÷ reported earnings per share over the trailing twelve months. Shown when no forward estimate is available. Coloured on the same 15x/30x scale as forward P/E.',
  avgVolume: 'Average daily volume over the last 3 months, in shares. Compare it against today’s volume to gauge unusual activity.',
} as const

const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: '$',
  EUR: '€',
  GBP: '£',
  JPY: '¥',
  CAD: 'C$',
  AUD: 'A$',
  HKD: 'HK$',
  CHF: 'CHF ',
}

function currencyPrefix(code?: string | null): string {
  const normalized = (code ?? '').trim().toUpperCase()
  if (!normalized) return '$'
  return CURRENCY_SYMBOLS[normalized] ?? `${normalized} `
}

function fmtMoney(value: number, code?: string | null): string {
  const prefix = currencyPrefix(code)
  const abs = Math.abs(value)
  if (abs >= 1e12) return `${prefix}${(value / 1e12).toFixed(2)}T`
  if (abs >= 1e9) return `${prefix}${(value / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `${prefix}${(value / 1e6).toFixed(1)}M`
  return `${prefix}${Math.round(value).toLocaleString()}`
}

function fmtShares(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `${(value / 1e6).toFixed(1)}M`
  if (abs >= 1e3) return `${(value / 1e3).toFixed(1)}K`
  return String(Math.round(value))
}

function isUsable(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
}

type Metric = {
  key: string
  label: string
  value: string
  tooltip: string
  /**
   * Omitted for metrics with no meaningful good/bad reading (market cap, average
   * volume), which keep the strip's default text colour. A scored metric that
   * lands between the bands is `neutral` and greys out, as intended.
   */
  quality?: MetricQuality
}

/**
 * Compact fundamentals strip shown under an asset's price, alongside the
 * technical-analysis and Signa rows.
 *
 * Renders nothing when the asset carries no usable fundamentals — indices,
 * futures and forex pairs have no market cap or earnings, so an empty strip
 * would be noise.
 */
export default function AssetFundamentals({
  asset,
  className = '',
}: {
  asset: Asset
  className?: string
}) {
  const fundamentals = asset.fundamentals
  const currency = fundamentals?.currency

  // Older classifier cache rows predate the fundamentals block but still carry
  // a flat market cap, so fall back to it rather than dropping the metric.
  const marketCap = isUsable(fundamentals?.market_cap)
    ? fundamentals.market_cap
    : isUsable(asset.market_cap)
      ? asset.market_cap
      : null

  const metrics: Metric[] = []

  if (marketCap !== null) {
    metrics.push({
      key: 'market-cap',
      label: 'Mkt cap',
      value: fmtMoney(marketCap, currency),
      tooltip: TOOLTIPS.marketCap,
    })
  }

  // Yahoo omits a forward P/E for loss-making companies, ETFs and indices.
  // Trailing P/E is the honest stand-in, so relabel rather than show nothing.
  if (isUsable(fundamentals?.forward_pe)) {
    metrics.push({
      key: 'pe',
      label: 'Fwd P/E',
      value: fundamentals.forward_pe.toFixed(1),
      tooltip: TOOLTIPS.forwardPE,
      quality: scoreMetric(fundamentals.forward_pe, PE_SCALE),
    })
  } else if (isUsable(fundamentals?.trailing_pe)) {
    metrics.push({
      key: 'pe',
      label: 'P/E (TTM)',
      value: fundamentals.trailing_pe.toFixed(1),
      tooltip: TOOLTIPS.trailingPE,
      quality: scoreMetric(fundamentals.trailing_pe, PE_SCALE),
    })
  }

  if (isUsable(fundamentals?.avg_volume)) {
    metrics.push({
      key: 'avg-volume',
      label: 'Avg vol',
      value: fmtShares(fundamentals.avg_volume),
      tooltip: TOOLTIPS.avgVolume,
    })
  }

  // Industry is the specific read ("Semiconductors"); sector is the broad one
  // ("Technology"). Prefer the specific label and keep the other in the tooltip.
  const sector = asset.sector?.trim() || null
  const industry = asset.industry?.trim() || null
  const classification = industry ?? sector
  const classificationTooltip =
    sector && industry && sector !== industry ? `${sector} · ${industry}` : (classification ?? '')

  if (metrics.length === 0 && !classification) {
    return null
  }

  return (
    <div
      data-testid="asset-fundamentals"
      className={`rounded-lg bg-zinc-100 px-2 py-1 text-[10px] text-zinc-700 dark:bg-zinc-800/70 dark:text-zinc-200 ${className}`.trim()}
    >
      {metrics.length > 0 && (
        <div
          className={`grid gap-x-3 gap-y-0.5 ${metrics.length === 1 ? 'grid-cols-1' : 'grid-cols-2'}`}
        >
          {metrics.map((metric) => (
            <div key={metric.key} className="flex items-baseline justify-between gap-1">
              <span
                title={metric.tooltip}
                className="shrink-0 cursor-help text-zinc-500 underline decoration-dotted underline-offset-2 dark:text-zinc-400"
              >
                {metric.label}
              </span>
              <span
                className={`truncate font-semibold tabular-nums ${
                  metric.quality ? metricQualityTextClass(metric.quality) : ''
                }`.trim()}
              >
                {metric.value}
              </span>
            </div>
          ))}
        </div>
      )}
      {classification && (
        <div
          title={classificationTooltip}
          className={`truncate text-zinc-500 dark:text-zinc-400 ${metrics.length > 0 ? 'mt-0.5' : ''}`.trim()}
        >
          {classification}
        </div>
      )}
    </div>
  )
}
