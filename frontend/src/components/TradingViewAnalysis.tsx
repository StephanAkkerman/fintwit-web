import type { AssetTechnicalAnalysis } from '../types'
import { directionTextClass } from '../utils/directionColor'

function formatCounts(value: number, label: string): string {
  return `${value} ${label}`
}

function formatRecommendation(value: string): string {
  const normalized = value.trim().replace(/_/g, ' ')
  return normalized ? normalized : 'Neutral'
}

export default function TradingViewAnalysis({
  analysis,
  className = '',
}: {
  analysis?: AssetTechnicalAnalysis | null
  className?: string
}) {
  const rows = [
    ['4H', analysis?.four_h],
    ['1D', analysis?.one_d],
  ].filter(([, item]) => Boolean(item)) as Array<[
    string,
    NonNullable<AssetTechnicalAnalysis['four_h']>,
  ]>

  if (rows.length === 0) {
    return null
  }

  return (
    <div className={`grid gap-1.5 ${className}`.trim()}>
      {rows.map(([label, item]) => (
        <div
          key={label}
          className="flex items-center justify-between gap-2 rounded-lg bg-zinc-100 px-2 py-1 text-[10px] text-zinc-700 dark:bg-zinc-800/70 dark:text-zinc-200"
        >
          <div className="flex min-w-0 items-center gap-1.5">
            <span className="shrink-0 rounded-full bg-zinc-200 px-1.5 py-0.5 font-semibold uppercase tracking-wide text-[9px] text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300">
              {label}
            </span>
            <span className={`truncate font-semibold ${directionTextClass(item.recommendation)}`}>
              {formatRecommendation(item.recommendation)}
            </span>
          </div>
          <span className="shrink-0 text-zinc-500 dark:text-zinc-400">
            {formatCounts(item.buy, 'buy')} · {formatCounts(item.neutral, 'neutral')} ·{' '}
            {formatCounts(item.sell, 'sell')}
          </span>
        </div>
      ))}
    </div>
  )
}
