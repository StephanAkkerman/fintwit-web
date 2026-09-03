import { usePortfolioInsights } from '../hooks/usePortfolioInsights'
import type { PortfolioDiversificationLabel, PortfolioFlagTone, PortfolioSector } from '../types'

const TONE_CLASS: Record<PortfolioFlagTone, string> = {
  bullish:
    'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300',
  bearish:
    'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-950/50 dark:text-rose-300',
  neutral:
    'border-zinc-300 bg-zinc-50 text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300',
}

const LABEL_TEXT: Record<PortfolioDiversificationLabel, string> = {
  unrated: 'Not enough data',
  concentrated: 'Concentrated',
  moderate: 'Moderately diversified',
  diversified: 'Well diversified',
}

// Cosmetic-only palette for the sector bars — the underlying sort order (by
// market value) is what actually carries meaning, not the color.
const SECTOR_COLORS = [
  'bg-sky-500',
  'bg-violet-500',
  'bg-amber-500',
  'bg-emerald-500',
  'bg-rose-500',
  'bg-cyan-500',
  'bg-fuchsia-500',
  'bg-lime-500',
]

function percent(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value.toFixed(1)}%`
}

function money(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })
}

function SectorRow({ sector, color }: { sector: PortfolioSector; color: string }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span className="font-medium text-zinc-700 dark:text-zinc-200">
          <span>{sector.sector}</span>
          <span className="ml-1.5 font-normal text-zinc-400">
            {sector.symbols.join(', ')}
          </span>
        </span>
        <span className="shrink-0 font-mono tabular-nums text-zinc-500">
          {money(sector.market_value)} · {percent(sector.weight_percent)}
        </span>
      </div>
      <div className="mt-1 h-1.5 rounded-full bg-zinc-100 dark:bg-zinc-900">
        <div
          className={`h-1.5 rounded-full ${color}`}
          style={{ width: `${Math.min(100, Math.max(0, sector.weight_percent))}%` }}
        />
      </div>
    </div>
  )
}

export default function PortfolioDiversification() {
  const { insights, loading, error } = usePortfolioInsights()
  const sectors = insights?.sectors ?? []
  const diversification = insights?.diversification

  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">
          Balance &amp; Sectors
        </h2>
        {diversification && diversification.label !== 'unrated' && (
          <span
            className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${TONE_CLASS[diversification.tone]}`}
          >
            {LABEL_TEXT[diversification.label]}
          </span>
        )}
      </div>

      {error && <p className="mb-2 text-sm text-rose-500">{error}</p>}

      {loading ? (
        <div className="h-32 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
      ) : sectors.length === 0 ? (
        <p className="text-sm text-zinc-500">
          No holdings yet — add a position to see sector allocation and how
          concentrated the portfolio is.
        </p>
      ) : (
        <>
          {diversification && (
            <div className="mb-4 grid gap-2 sm:grid-cols-2">
              <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-2 dark:border-zinc-700 dark:bg-zinc-900/50">
                <div className="text-[11px] text-zinc-500">Largest holding</div>
                <div className="text-sm font-semibold">
                  {diversification.top_holding
                    ? `${diversification.top_holding.symbol} · ${percent(diversification.top_holding.weight_percent)}`
                    : '—'}
                </div>
              </div>
              <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-2 dark:border-zinc-700 dark:bg-zinc-900/50">
                <div className="text-[11px] text-zinc-500">Largest sector</div>
                <div className="text-sm font-semibold">
                  {diversification.top_sector
                    ? `${diversification.top_sector.sector} · ${percent(diversification.top_sector.weight_percent)}`
                    : '—'}
                </div>
              </div>
            </div>
          )}

          <div className="space-y-3">
            {sectors.map((sector, index) => (
              <SectorRow
                key={sector.sector}
                sector={sector}
                color={SECTOR_COLORS[index % SECTOR_COLORS.length]}
              />
            ))}
          </div>

          {diversification && (
            <p className="mt-3 text-[11px] text-zinc-400">
              Effective holdings ≈{' '}
              {diversification.effective_holdings != null
                ? diversification.effective_holdings.toFixed(1)
                : '—'}{' '}
              · effective sectors ≈{' '}
              {diversification.effective_sectors != null
                ? diversification.effective_sectors.toFixed(1)
                : '—'}
            </p>
          )}
        </>
      )}
    </section>
  )
}
