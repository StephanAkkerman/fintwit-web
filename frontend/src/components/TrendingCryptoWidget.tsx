import { useEffect, useState } from 'react'

interface TrendingCrypto {
  name: string
  symbol: string
  slug: string
  price: number
  change_24h: number
  volume_24h: number
  website: string | null
}

export default function TrendingCryptoWidget() {
  const [trending, setTrending] = useState<TrendingCrypto[]>([])
  const [error, setError] = useState(false)

  useEffect(() => {
    fetch('/api/trending-crypto')
      .then((res) => {
        if (!res.ok) throw new Error('Network response was not ok')
        return res.json()
      })
      .then((data) => setTrending(data))
      .catch((err) => {
        console.error('Error fetching trending crypto:', err)
        setError(true)
      })
  }, [])

  if (error) {
    return (
      <div className="p-4 rounded-xl bg-red-900/20 border border-red-500/50 mb-4">
        <p className="text-sm font-medium text-red-400">Error fetching trending crypto</p>
      </div>
    )
  }

  if (trending.length === 0) {
    return (
      <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 animate-pulse mb-4 h-32" />
    )
  }

  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-4 mb-4">
      <h2 className="text-lg font-bold mb-3 flex items-center gap-2">
        <span className="text-xl">🔥</span> Trending Crypto
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-zinc-500 uppercase bg-zinc-50 dark:bg-zinc-900/50 border-b border-zinc-200 dark:border-zinc-800">
            <tr>
              <th className="px-3 py-2">Coin</th>
              <th className="px-3 py-2 text-right">Price</th>
              <th className="px-3 py-2 text-right">24h %</th>
            </tr>
          </thead>
          <tbody>
            {trending.slice(0, 5).map((coin) => (
              <tr key={coin.symbol} className="border-b border-zinc-100 dark:border-zinc-800/50 last:border-0 hover:bg-zinc-50 dark:hover:bg-zinc-900/30 transition-colors">
                <td className="px-3 py-2 font-medium">
                  {coin.website ? (
                    <a href={coin.website} target="_blank" rel="noreferrer" className="hover:underline flex items-center gap-1.5">
                      {coin.name} <span className="text-zinc-500 text-xs">{coin.symbol}</span>
                    </a>
                  ) : (
                    <span className="flex items-center gap-1.5">
                      {coin.name} <span className="text-zinc-500 text-xs">{coin.symbol}</span>
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-right font-mono">
                  ${coin.price?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 }) ?? 'N/A'}
                </td>
                <td className={`px-3 py-2 text-right font-mono ${coin.change_24h && coin.change_24h > 0 ? 'text-green-500' : coin.change_24h && coin.change_24h < 0 ? 'text-red-500' : 'text-zinc-500'}`}>
                  {coin.change_24h && coin.change_24h > 0 ? '+' : ''}{coin.change_24h?.toFixed(2) ?? 'N/A'}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
