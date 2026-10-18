import { useEffect, useState } from 'react'
import type { PutCallRatios } from '../types'

// Cboe publishes one file per session, so polling faster than the backend's
// hourly cache only re-reads the same numbers.
const POLL_INTERVAL_MS = 3_600_000

export function usePutCallRatio() {
  const [data, setData] = useState<PutCallRatios | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    async function load() {
      try {
        const res = await fetch('/api/options/put-call', { signal: controller.signal })
        if (!res.ok) throw new Error('Failed to fetch put/call ratios')
        const payload = (await res.json()) as Partial<PutCallRatios> | null
        setData({
          date: String(payload?.date ?? ''),
          ratios: Array.isArray(payload?.ratios) ? payload.ratios : [],
          volume: payload?.volume ?? {},
          sentiment: payload?.sentiment ?? null,
          thresholds: payload?.thresholds ?? { fear: 0.8, greed: 0.5 },
          history: Array.isArray(payload?.history) ? payload.history : [],
          source: String(payload?.source ?? 'cboe'),
        })
        setError(false)
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return
        setError(true)
      } finally {
        setLoading(false)
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
