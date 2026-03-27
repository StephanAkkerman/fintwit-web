import { useEffect, useState } from 'react'

export interface TrendingCoin {
  symbol: string
  slug: string
  name: string
  price: number
  change_percent: number
  volume: number
}

export function useTrendingCrypto() {
  const [data, setData] = useState<TrendingCoin[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let mounted = true
    const fetchTrending = async () => {
      try {
        const res = await fetch('/api/trending-crypto')
        if (!res.ok) {
          throw new Error('Failed to fetch trending crypto')
        }
        const json = await res.json()
        if (mounted) {
          setData(json)
          setLoading(false)
        }
      } catch (err: any) {
        if (mounted) {
          setError(err.message)
          setLoading(false)
        }
      }
    }

    fetchTrending()

    // Optional: Refresh data periodically
    const interval = setInterval(fetchTrending, 60000)

    return () => {
      mounted = false
      clearInterval(interval)
    }
  }, [])

  return { data, error, loading }
}
