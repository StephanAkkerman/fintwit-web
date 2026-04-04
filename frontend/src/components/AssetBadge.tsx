import type { Asset } from '../types'

export default function AssetBadge({ asset }: { asset: Asset }) {
  if (!asset.financials) {
    return (
      <span className="px-2 py-1 rounded bg-zinc-100 dark:bg-zinc-800 text-xs font-medium text-zinc-700 dark:text-zinc-300">
        ${asset.symbol} {asset.name ? `(${asset.name})` : ''}
      </span>
    )
  }

  const { price, change_percent, website } = asset.financials
  const isPositive = change_percent >= 0
  const changeColor = isPositive ? 'text-green-500' : 'text-red-500'
  const changeSign = isPositive ? '+' : ''

  return (
    <a
      href={website}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors text-sm text-zinc-900 dark:text-zinc-100"
    >
      <div className="flex flex-col">
        <span className="font-bold">${asset.symbol}</span>
        {asset.name && <span className="text-[10px] text-zinc-500 truncate max-w-[100px]">{asset.name}</span>}
      </div>
      <div className="flex flex-col items-end border-l border-zinc-200 dark:border-zinc-700 pl-2">
        <span className="font-mono">${price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</span>
        <span className={`text-[10px] font-bold ${changeColor}`}>
          {changeSign}{change_percent.toFixed(2)}%
        </span>
      </div>
    </a>
  )
}
