import type { Asset } from '../types'
import SignaSignal from './SignaSignal'
import TradingViewAnalysis from './TradingViewAnalysis'

export default function AssetBadge({ asset }: { asset: Asset }) {
  if (!asset.financials) {
    return (
      <span className="px-2 py-1 rounded bg-zinc-100 dark:bg-zinc-800 text-xs font-medium text-zinc-700 dark:text-zinc-300">
        ${asset.symbol} {asset.name ? `(${asset.name})` : ''}
      </span>
    )
  }

  const { price, last_close, change_percent, website, technical_analysis, signa } = asset.financials
  const isPositive = change_percent >= 0
  const changeColor = isPositive ? 'text-green-500' : 'text-red-500'
  const changeSign = isPositive ? '+' : ''

  return (
    <a
      href={website}
      target="_blank"
      rel="noreferrer"
      className="inline-flex flex-col gap-2 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm text-zinc-900 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:hover:bg-zinc-700"
    >
      <div className="flex items-center gap-2">
        <div className="flex min-w-0 flex-col">
          <span className="font-bold">${asset.symbol}</span>
          {asset.name && (
            <span className="max-w-[140px] truncate text-[10px] text-zinc-500">{asset.name}</span>
          )}
        </div>
        <div className="ml-auto flex flex-col items-end border-l border-zinc-200 pl-2 dark:border-zinc-700">
          <span className="font-mono">
            ${price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
          </span>
          <span className={`text-[10px] font-bold ${changeColor}`}>
            {changeSign}
            {change_percent.toFixed(2)}%
          </span>
          {typeof last_close === 'number' && (
            <span className="text-[9px] text-zinc-500 dark:text-zinc-400">
              Last close ${last_close.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
            </span>
          )}
        </div>
      </div>
      <TradingViewAnalysis analysis={technical_analysis} />
      <SignaSignal signal={signa} className="mt-1.5" />
    </a>
  )
}
