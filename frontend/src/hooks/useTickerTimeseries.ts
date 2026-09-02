import { useEffect, useState } from 'react'
import type { TickerTimeseries } from '../types'

export function useTickerTimeseries(ticker: string | null, windowHours = 168) {
  const [data, setData] = useState<TickerTimeseries | null>(null)
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
    const params = new URLSearchParams({ ticker, window_hours: String(windowHours) })
    fetch(`/api/overview/ticker-timeseries?${params}`, { signal: controller.signal })
      .then((r) => {
        if (!r.ok) throw new Error('ticker-timeseries')
        return r.json()
      })
      .then((p) => setData(p ?? null))
      .catch((e) => {
        if (e.name !== 'AbortError') setError(true)
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [ticker, windowHours])

  return { data, loading, error }
}
