import { useEffect, useState } from 'react'
import type { StockFearGreedData } from '../types'

export function useStockFearGreed() {
  const [data, setData] = useState<StockFearGreedData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(false)

    fetch('/api/stocks/fear-greed', { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch stock Fear & Greed index')
        return res.json()
      })
      .then((payload) => {
        if (
          payload &&
          typeof payload === 'object' &&
          !Array.isArray(payload) &&
          typeof payload.value === 'number' &&
          typeof payload.status === 'string'
        ) {
          setData(payload)
        } else {
          setError(true)
        }
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(true)
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [])

  return { data, loading, error }
}
