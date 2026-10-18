import { useEffect, useState } from 'react'
import type { EarningsResults } from '../types'

const EMPTY: EarningsResults = {
  start_date: '',
  end_date: '',
  results: [],
  summary: { reported: 0, beat: 0, miss: 0, inline: 0 },
  source: 'nasdaq',
}

// Reports land before the open and after the close; the backend caches for
// 15 minutes, so polling on that cadence picks up the after-hours batch.
const POLL_INTERVAL_MS = 900_000

export function useEarningsResults(days = 5) {
  const [data, setData] = useState<EarningsResults>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    async function load() {
      try {
        const res = await fetch(`/api/earnings/results?days=${days}`, { signal: controller.signal })
        if (!res.ok) throw new Error('Failed to fetch earnings results')
        const payload = (await res.json()) as Partial<EarningsResults> | null
        setData(
          payload && Array.isArray(payload.results)
            ? { ...EMPTY, ...payload, summary: payload.summary ?? EMPTY.summary }
            : EMPTY,
        )
        setError(false)
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return
        setError(true)
      } finally {
        setLoading(false)
      }
    }

    setLoading(true)
    void load()
    const id = setInterval(() => void load(), POLL_INTERVAL_MS)
    return () => {
      controller.abort()
      clearInterval(id)
    }
  }, [days])

  return { data, loading, error }
}
