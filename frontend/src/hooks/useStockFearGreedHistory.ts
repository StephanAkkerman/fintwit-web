import { useEffect, useState } from 'react'
import type { StockFearGreedHistory, StockFearGreedWindow } from '../types'

export function useStockFearGreedHistory(days: StockFearGreedWindow) {
  const [data, setData] = useState<StockFearGreedHistory | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(false)

    fetch(`/api/stocks/fear-greed/history?days=${days}`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch stock Fear & Greed history')
        return res.json()
      })
      .then((payload) => {
        if (
          payload &&
          typeof payload === 'object' &&
          !Array.isArray(payload) &&
          Array.isArray(payload.points)
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
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [days])

  return { data, loading, error }
}
