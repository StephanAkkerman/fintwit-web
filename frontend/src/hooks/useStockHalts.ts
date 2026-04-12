import { useEffect, useState } from 'react'
import type { StockHaltItem } from '../types'

export function useStockHalts() {
  const [data, setData] = useState<StockHaltItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(false)

    fetch('/api/stock-halts', { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch stock halts')
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
