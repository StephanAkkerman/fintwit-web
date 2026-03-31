import { useEffect, useState } from 'react'

export type TrendingCrypto = {
  symbol: string
  slug: string
  price: number
  change_percent: number
  volume: number
  website: string
}

export default function TrendingCryptoWidget() {
  const [data, setData] = useState<TrendingCrypto[] | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/trending-crypto')
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch trending crypto')
        return res.json()
      })
      .then((json: TrendingCrypto[]) => {
        setData(json)
      })
      .catch((err) => {
        console.error(err)
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  if (loading) {
    return (
      <div className="bg-zinc-100 dark:bg-zinc-900 rounded-2xl p-4 my-4 animate-pulse">
        <div className="h-6 w-32 bg-zinc-300 dark:bg-zinc-700 rounded mb-4"></div>
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-4 bg-zinc-300 dark:bg-zinc-700 rounded"></div>
          ))}
        </div>
      </div>
    )
  }

  if (!data || data.length === 0) return null

  return (
    <div className="bg-zinc-100 dark:bg-zinc-900 rounded-2xl p-4 my-4">
      <h2 className="text-lg font-bold mb-3 flex items-center">
        🔥 Trending Crypto
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-zinc-500 uppercase bg-zinc-200 dark:bg-zinc-800 rounded-t-lg">
            <tr>
              <th scope="col" className="px-3 py-2 rounded-tl-lg">Coin</th>
              <th scope="col" className="px-3 py-2">Price</th>
              <th scope="col" className="px-3 py-2">24h Change</th>
              <th scope="col" className="px-3 py-2 rounded-tr-lg">Volume</th>
            </tr>
          </thead>
          <tbody>
            {data.slice(0, 5).map((item) => {
              const isPositive = item.change_percent >= 0
              return (
                <tr key={item.slug} className="border-b border-zinc-200 dark:border-zinc-800 last:border-0">
                  <td className="px-3 py-2 font-medium">
                    <a href={item.website} target="_blank" rel="noopener noreferrer" className="hover:underline">
                      {item.symbol}
                    </a>
                  </td>
                  <td className="px-3 py-2">
                    ${item.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 })}
                  </td>
                  <td className={`px-3 py-2 ${isPositive ? 'text-green-500' : 'text-red-500'}`}>
                    {isPositive ? '+' : ''}{item.change_percent.toFixed(2)}%
                  </td>
                  <td className="px-3 py-2 text-zinc-500">
                    ${(item.volume / 1000000).toFixed(1)}M
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
