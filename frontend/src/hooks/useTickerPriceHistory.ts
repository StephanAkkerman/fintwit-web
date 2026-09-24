import { useEffect, useState } from 'react'
import type { TickerPriceHistory } from '../types'

export function useTickerPriceHistory(ticker: string | null) {
  const [data, setData] = useState<TickerPriceHistory | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!ticker) {
      setData(null)
      setLoading(false)
      setError(false)
      return
    }

    const controller = new AbortController()
    setLoading(true)
    setError(false)
    const params = new URLSearchParams({ ticker })
    fetch(`/api/overview/ticker-price-history?${params}`, { signal: controller.signal })
      .then((r) => {
        if (!r.ok) throw new Error('ticker-price-history')
        return r.json()
      })
      .then((p) => setData(p ?? null))
      .catch((e) => {
        if (e.name !== 'AbortError') setError(true)
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [ticker])

  return { data, loading, error }
}
