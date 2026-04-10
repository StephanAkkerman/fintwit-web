import { useEffect, useState } from 'react'
import type { StockMarketHoursItem } from '../types'

export function useStockMarketHours() {
  const [data, setData] = useState<StockMarketHoursItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(false)

    fetch('/api/stocks/market-hours', { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch stock market hours')
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
  }, [])

  return { data, loading, error }
}
