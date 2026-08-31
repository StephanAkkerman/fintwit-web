import { usePortfolioInsights } from '../hooks/usePortfolioInsights'
import type {
  PortfolioAssetFlag,
  PortfolioAssetStats,
  PortfolioInsightPosition,
} from '../types'

const TONE_CLASS: Record<PortfolioAssetFlag['tone'], string> = {
  bullish:
    'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300',
  bearish:
    'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-950/50 dark:text-rose-300',
  neutral:
    'border-zinc-300 bg-zinc-50 text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300',
}

// Flags carry an icon as well as a colour so the state never rests on hue alone.
const TONE_ICON: Record<PortfolioAssetFlag['tone'], string> = {
  bullish: '▲',
  bearish: '▼',
  neutral: '•',
}

function money(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function percent(value: number | null | undefined, signed = true): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${signed && value >= 0 ? '+' : ''}${value.toFixed(1)}%`
}

function FlagBadge({ flag }: { flag: PortfolioAssetFlag }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${TONE_CLASS[flag.tone]}`}
    >
      <span aria-hidden="true">{TONE_ICON[flag.tone]}</span>
      {flag.label}
    </span>
  )
}

function RangeBar({ stats }: { stats: PortfolioAssetStats }) {
  const position = stats.range_position_52w
  if (position == null) return <span className="text-zinc-400">—</span>

  return (
    <div
      className="min-w-[110px]"
      title={`52-week range ${money(stats.week_52_low?.value)} – ${money(stats.week_52_high?.value)}`}
    >
      <div className="relative h-1.5 rounded-full bg-zinc-200 dark:bg-zinc-800">
        <div
          className="absolute top-1/2 h-3 w-0.5 -translate-y-1/2 rounded-full bg-zinc-900 dark:bg-zinc-100"
          style={{ left: `${position}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-zinc-400 tabular-nums">
        <span>{money(stats.week_52_low?.value)}</span>
        <span>{money(stats.week_52_high?.value)}</span>
      </div>
    </div>
  )
}

function AssetRow({ position }: { position: PortfolioInsightPosition }) {
  const stats = position.stats

  return (
    <tr className="border-t border-zinc-100 align-top dark:border-zinc-900">
      <td className="py-2">
        <div className="font-semibold text-zinc-900 dark:text-zinc-100">
          {position.symbol}
        </div>
        <div className="text-[11px] text-zinc-500 tabular-nums">
          {position.quantity} @ {money(position.avg_cost)}
        </div>
      </td>
      <td className="py-2 text-right font-mono tabular-nums">
        {money(position.market_price)}
      </td>
      <td className="py-2 text-right font-mono tabular-nums">
        {percent(position.weight_percent, false)}
      </td>
      <td
        className={`py-2 text-right font-mono tabular-nums ${
          position.unrealized_pnl >= 0
            ? 'text-emerald-600 dark:text-emerald-400'
            : 'text-rose-600 dark:text-rose-400'
        }`}
      >
        {money(position.unrealized_pnl)}
        <div className="text-[11px]">{percent(position.unrealized_pnl_percent)}</div>
      </td>
      <td className="py-2 text-right font-mono tabular-nums">
        {stats ? percent(stats.from_ath_percent) : '—'}
        {stats?.all_time_high && (
          <div className="text-[10px] font-normal text-zinc-400">
            {money(stats.all_time_high.value)} · {stats.all_time_high.date}
          </div>
        )}
      </td>
      <td className="py-2 text-right font-mono tabular-nums">
        {stats ? percent(stats.from_atl_percent) : '—'}
        {stats?.all_time_low && (
          <div className="text-[10px] font-normal text-zinc-400">
            {money(stats.all_time_low.value)} · {stats.all_time_low.date}
          </div>
        )}
      </td>
      <td className="py-2">{stats ? <RangeBar stats={stats} /> : '—'}</td>
      <td className="py-2">
        <div className="flex flex-wrap justify-end gap-1">
          {(stats?.flags ?? []).map((flag) => (
            <FlagBadge key={flag.code} flag={flag} />
          ))}
        </div>
      </td>
    </tr>
  )
}

export default function PortfolioAssetInsights() {
  const { insights, loading, error } = usePortfolioInsights()
  const positions = insights?.positions ?? []
  const highlights = insights?.highlights ?? []

  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">
          Asset Context
        </h2>
        {insights && (
          <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
            {insights.source === 'ibkr' ? 'IBKR positions' : 'Tracked positions'}
          </span>
        )}
      </div>

      {error && <p className="mb-2 text-sm text-rose-500">{error}</p>}

      {loading ? (
        <div className="h-32 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
      ) : positions.length === 0 ? (
        <p className="text-sm text-zinc-500">
          No holdings yet — add a position to see how each asset sits against its
          all-time and 52-week range.
        </p>
      ) : (
        <>
          {highlights.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-1.5">
              {highlights.map((highlight) => (
                <span
                  key={`${highlight.symbol}-${highlight.code}`}
                  className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${TONE_CLASS[highlight.tone]}`}
                >
                  <span aria-hidden="true">{TONE_ICON[highlight.tone]}</span>
                  <span className="font-bold">{highlight.symbol}</span>
                  {highlight.label}
                </span>
              ))}
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-zinc-200 text-zinc-500 dark:border-zinc-800">
                <tr>
                  <th className="py-2">Asset</th>
                  <th className="py-2 text-right">Price</th>
                  <th className="py-2 text-right">Weight</th>
                  <th className="py-2 text-right">Unrealized</th>
                  <th className="py-2 text-right">vs ATH</th>
                  <th className="py-2 text-right">vs ATL</th>
                  <th className="py-2">52-week range</th>
                  <th className="py-2 text-right">Signals</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((position) => (
                  <AssetRow key={position.symbol} position={position} />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}
