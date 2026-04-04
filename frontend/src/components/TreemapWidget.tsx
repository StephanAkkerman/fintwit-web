import { useTreemap } from '../hooks/useTreemap'

export default function TreemapWidget() {
  const { data, loading, error } = useTreemap()

  if (loading) {
    return (
      <div className="bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-4 flex flex-col space-y-2 mb-4">
        <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider">Market Treemap</h2>
        <div className="animate-pulse h-40 bg-zinc-200 dark:bg-zinc-800 rounded-md w-full"></div>
      </div>
    )
  }

  if (error || !data || !data.data) {
    return null
  }

  // Take top 10 coins
  const coins = data.data.slice(0, 10)

  return (
    <div className="bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-4 flex flex-col space-y-2 mb-4">
      <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider mb-2">Market Treemap</h2>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        {coins.map((coin) => {
          const isPositive = coin.ch >= 0
          const colorClass = isPositive
            ? 'bg-green-500/10 border-green-500/20 text-green-700 dark:text-green-400'
            : 'bg-red-500/10 border-red-500/20 text-red-700 dark:text-red-400'

          return (
            <div
              key={coin.s}
              className={`flex flex-col items-center justify-center p-3 rounded-lg border ${colorClass}`}
            >
              <span className="font-bold text-lg">{coin.s}</span>
              <span className="text-xs opacity-80">{isPositive ? '+' : ''}{coin.ch.toFixed(2)}%</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
