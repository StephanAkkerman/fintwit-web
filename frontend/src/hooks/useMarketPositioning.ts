import { useEffect, useState } from 'react'
import type { MarketPositioning } from '../types'

// COT data is weekly and the price inputs are daily, so there's no point
// polling faster than the backend cache refreshes.
const POLL_INTERVAL_MS = 3_600_000

export function useMarketPositioning() {
  const [data, setData] = useState<MarketPositioning | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    async function load() {
      try {
        const res = await fetch('/api/market/positioning', { signal: controller.signal })
        if (!res.ok) throw new Error('Failed to fetch market positioning')
        const payload = (await res.json()) as Partial<MarketPositioning> | null
        setData({
          futures: Array.isArray(payload?.futures) ? payload.futures : null,
          cta: payload?.cta ?? null,
          concentration: payload?.concentration ?? null,
          as_of: String(payload?.as_of ?? ''),
        })
        setError(false)
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return
        setError(true)
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }

    void load()
    const id = setInterval(() => void load(), POLL_INTERVAL_MS)
    return () => {
      controller.abort()
      clearInterval(id)
    }
  }, [])

  return { data, loading, error }
}
