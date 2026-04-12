import { useEffect, useState } from 'react'
import type { NftTrendingItem } from '../types'

export function useTrendingNfts(limit = 10) {
  const [data, setData] = useState<NftTrendingItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(false)

    fetch(`/api/nfts/trending?limit=${limit}`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch trending NFTs')
        return res.json()
      })
      .then((payload) => {
        setData(Array.isArray(payload) ? payload : [])
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(true)
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [limit])

  return { data, loading, error }
}
