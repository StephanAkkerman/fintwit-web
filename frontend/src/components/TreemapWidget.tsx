import { useMemo } from 'react'
import { useTreemap } from '../hooks/useTreemap'

const USD_FORMATTER = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
});

export default function TreemapWidget() {
  const { data, loading, error } = useTreemap()

  if (error) return null

  // Sort by market cap and take top 10
  const topCoins = useMemo(() => {
    return data?.data
      ? [...data.data].sort((a, b) => b.mc - a.mc).slice(0, 10)
      : []
  }, [data])

  return (
    <div className="bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-4 flex flex-col space-y-3 mb-4">
      <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider">
        Top Coins by Market Cap
      </h2>

      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="animate-pulse h-16 bg-zinc-200 dark:bg-zinc-800 rounded-lg"></div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          {topCoins.map((coin) => {
            const isPositive = coin.ch >= 0;
            const changeColor = isPositive ? 'text-green-500' : 'text-red-500';

            // Format price based on magnitude
            const priceStr = coin.p < 1
              ? `$${coin.p.toPrecision(3)}`
              : USD_FORMATTER.format(coin.p);

            return (
              <div
                key={coin.s}
                className="flex flex-col items-center justify-center p-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 shadow-sm"
              >
                <div className="font-bold text-zinc-900 dark:text-zinc-100 text-sm">{coin.s}</div>
                <div className="text-xs text-zinc-600 dark:text-zinc-400">{priceStr}</div>
                <div className={`text-xs font-medium ${changeColor}`}>
                  {isPositive ? '+' : ''}{coin.ch.toFixed(2)}%
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  )
}
