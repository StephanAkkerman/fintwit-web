import { useTrendingCrypto } from '../hooks/useTrendingCrypto'

export default function TrendingCryptoWidget() {
  const { data, loading, error } = useTrendingCrypto()

  if (loading) {
    return (
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/50 p-4 mb-4">
        <p className="text-zinc-500 animate-pulse text-sm">Loading trending crypto...</p>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-900/20 p-4 mb-4">
        <p className="text-red-600 dark:text-red-400 text-sm">Unavailable: Trending Crypto</p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4 mb-4">
      <h2 className="text-lg font-bold mb-3">Trending Crypto</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left whitespace-nowrap">
          <thead className="text-xs text-zinc-500 uppercase border-b border-zinc-200 dark:border-zinc-800">
            <tr>
              <th scope="col" className="px-2 py-2">Coin</th>
              <th scope="col" className="px-2 py-2 text-right">Price</th>
              <th scope="col" className="px-2 py-2 text-right">24h Change</th>
            </tr>
          </thead>
          <tbody>
            {data.slice(0, 5).map((coin) => (
              <tr key={coin.slug} className="border-b border-zinc-100 dark:border-zinc-800 last:border-0 hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
                <td className="px-2 py-3">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{coin.name}</span>
                    <span className="text-zinc-500 text-xs bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded">{coin.symbol}</span>
                  </div>
                </td>
                <td className="px-2 py-3 text-right tabular-nums">
                  ${coin.price?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 })}
                </td>
                <td className="px-2 py-3 text-right">
                  <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium tabular-nums ${coin.change_percent >= 0 ? 'bg-green-100 text-green-700 dark:bg-green-400/10 dark:text-green-400' : 'bg-red-100 text-red-700 dark:bg-red-400/10 dark:text-red-400'}`}>
                    {coin.change_percent >= 0 ? '+' : ''}{coin.change_percent?.toFixed(2)}%
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
