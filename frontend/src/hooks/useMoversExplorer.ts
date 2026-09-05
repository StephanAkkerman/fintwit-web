import { useEffect, useState } from 'react'
import type { Market, MoverCategory, MoversResponse } from '../types'

export function useMoversExplorer(market: Market, category: MoverCategory) {
  const [data, setData] = useState<MoversResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(false)

    fetch(`/api/markets/movers?market=${market}&category=${category}`, {
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error('movers fetch failed')
        return res.json() as Promise<MoversResponse>
      })
      .then((payload) => setData(payload))
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(true)
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [market, category])

  return { data, loading, error }
}
