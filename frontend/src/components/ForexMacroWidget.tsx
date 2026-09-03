import { useMemo } from 'react'
import { useForexMacroSnapshot } from '../hooks/useForexMacroSnapshot'
import type { ForexMacroCurve, ForexMacroIndex } from '../types'

function formatPercent(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'N/A'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function formatYield(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'N/A'
  return `${value.toFixed(2)}%`
}

function formatLargeNumber(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'N/A'

  const absValue = Math.abs(value)
  if (absValue >= 1_000_000_000_000) return `${(value / 1_000_000_000_000).toFixed(2)}T`
  if (absValue >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B`
  if (absValue >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`
  if (absValue >= 1_000) return `${(value / 1_000).toFixed(2)}K`
  return value.toFixed(2)
}

function formatPrice(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'N/A'

  // Use localized formatting for large prices, keep two decimals
  try {
    return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  } catch (e) {
    return value.toFixed(2)
  }
}

function curveColor(label: string): string {
  return label.toUpperCase() === 'US'
    ? 'from-cyan-500/20 to-cyan-500/5'
    : 'from-rose-500/20 to-rose-500/5'
}

function CurveCard({ curve }: { curve: ForexMacroCurve }) {
  const maxYield = Math.max(...curve.points.map((point) => point.yield_percent), 0.01)

  return (
    <article className={`rounded-xl border border-zinc-200 bg-gradient-to-br p-3 dark:border-zinc-800 ${curveColor(curve.label)}`}>
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{curve.label} Yield Curve</p>
          <p className="text-[11px] text-zinc-500">
            {typeof curve.spread_2s10s === 'number' ? `2s10s spread ${curve.spread_2s10s.toFixed(2)}%` : '2s10s spread N/A'}
          </p>
        </div>
        <span className="rounded-full bg-white/70 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 shadow-sm dark:bg-zinc-950/70 dark:text-zinc-300">
          TradingView
        </span>
      </div>

      <div className="space-y-2">
        {curve.points.map((point) => {
          const width = Math.max(6, Math.round((point.yield_percent / maxYield) * 100))

          return (
            <div key={`${curve.label}-${point.maturity}`} className="grid grid-cols-[3rem_1fr_4rem] items-center gap-2 text-xs">
              <span className="font-mono text-zinc-500">{point.maturity}</span>
              <div className="h-2 overflow-hidden rounded-full bg-white/60 dark:bg-zinc-950/40">
                <div
                  className="h-full rounded-full bg-zinc-900 dark:bg-zinc-100"
                  style={{ width: `${width}%` }}
                />
              </div>
              <span className="text-right font-mono text-zinc-700 dark:text-zinc-200">
                {formatYield(point.yield_percent)}
              </span>
            </div>
          )
        })}
      </div>
    </article>
  )
}

function IndexRow({ index }: { index: ForexMacroIndex }) {
  const change = formatPercent(index.change_percent)
  const changeClass =
    typeof index.change_percent === 'number'
      ? index.change_percent > 0
        ? 'text-emerald-500'
        : index.change_percent < 0
          ? 'text-rose-500'
          : 'text-zinc-500'
      : 'text-zinc-500'

  const valueLabel = index.category === 'crypto' ? formatLargeNumber(index.price) : formatPrice(index.price)
  const href = index.website || '#'

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="block cursor-pointer rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 transition-colors hover:border-blue-300 hover:bg-blue-50/50 dark:border-zinc-800 dark:bg-zinc-900/60 dark:hover:border-blue-600 dark:hover:bg-blue-950/30"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{index.name}</p>
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">{index.symbol}</p>
        </div>
        <div className="text-right text-xs">
          <p className="font-semibold text-zinc-800 dark:text-zinc-200">{valueLabel}</p>
          <p className={`font-semibold ${changeClass}`}>{change}</p>
        </div>
      </div>
    </a>
  )
}

export default function ForexMacroWidget() {
  const { data, loading, error } = useForexMacroSnapshot()

  const curves = useMemo(() => data?.yield_curves ?? [], [data])
  const cryptoIndices = useMemo(() => data?.crypto_indices ?? [], [data])
  const stockForexIndices = useMemo(() => data?.stock_forex_indices ?? data?.fx_indices ?? [], [data])
  const stockForexVisible = data?.stock_forex_visible ?? true

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Macro Snapshot</h2>
          <p className="text-[11px] text-zinc-500">Yield curves and FX indices</p>
        </div>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          TradingView
        </span>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="h-52 animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load macro snapshot.</p>
      ) : curves.length === 0 && cryptoIndices.length === 0 && stockForexIndices.length === 0 ? (
        <p className="text-sm text-zinc-500">No macro snapshot data available right now.</p>
      ) : (
        <div className="space-y-4">
          {data?.as_of ? (
            <p className="text-[11px] text-zinc-500">As of {new Date(data.as_of).toLocaleString()}</p>
          ) : null}

          <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
            <div className="space-y-3">
              {curves.map((curve) => (
                <CurveCard key={curve.label} curve={curve} />
              ))}
            </div>

            <div className="space-y-3">
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900/60">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Crypto Indices</p>
                    <p className="text-[11px] text-zinc-500">Crypto market cap and dominance snapshots</p>
                  </div>
                  <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-950 dark:text-zinc-300">
                    {cryptoIndices.length}
                  </span>
                </div>

                <div className="space-y-2">
                  {cryptoIndices.map((index) => (
                    <IndexRow key={index.symbol} index={{ ...index, category: 'crypto' }} />
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900/60">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Stock & Forex Indices</p>
                    <p className="text-[11px] text-zinc-500">Legacy TradingView index panel</p>
                  </div>
                  <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-950 dark:text-zinc-300">
                    {stockForexVisible ? stockForexIndices.length : 'Closed'}
                  </span>
                </div>

                {!stockForexVisible ? (
                  <p className="text-sm text-zinc-500">
                    US market closed right now, so the legacy stock/forex index panel is hidden.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {stockForexIndices.map((index) => {
                      const category =
                        index.symbol === 'DXY' ||
                        index.symbol === 'EXY' ||
                        index.symbol === 'BXY' ||
                        index.symbol === 'JXY'
                          ? 'forex'
                          : 'stock'

                      return <IndexRow key={index.symbol} index={{ ...index, category }} />
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}