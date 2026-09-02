import type { AssetStocktwitsSentiment } from '../types'

export default function StocktwitsSentiment({
  sentiment,
  className = '',
}: {
  sentiment?: AssetStocktwitsSentiment | null
  className?: string
}) {
  if (!sentiment || typeof sentiment.bullish_percent !== 'number') {
    return null
  }

  const bullish = Math.round(sentiment.bullish_percent)
  const bearish =
    typeof sentiment.bearish_percent === 'number'
      ? Math.round(sentiment.bearish_percent)
      : 100 - bullish
  const isBullish = bullish >= bearish
  const colorClass = isBullish
    ? 'text-emerald-600 dark:text-emerald-400'
    : 'text-rose-600 dark:text-rose-400'

  return (
    <div className={`grid gap-1.5 ${className}`.trim()}>
      <div className="flex items-center justify-between gap-2 rounded-lg bg-zinc-100 px-2 py-1 text-[10px] text-zinc-700 dark:bg-zinc-800/70 dark:text-zinc-200">
        <div className="flex min-w-0 items-center gap-1.5">
          <span className="shrink-0 rounded-full bg-zinc-200 px-1.5 py-0.5 font-semibold uppercase tracking-wide text-[9px] text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300">
            StockTwits
          </span>
          <span className={`truncate font-semibold ${colorClass}`}>
            {isBullish ? 'Bullish' : 'Bearish'}
          </span>
        </div>
        <span className="shrink-0 text-zinc-500 dark:text-zinc-400">
          {bullish}% / {bearish}%
        </span>
      </div>
    </div>
  )
}
