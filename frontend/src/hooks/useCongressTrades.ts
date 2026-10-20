import { useEffect, useState } from 'react'
import type { CongressTrades } from '../types'

// Filings land a few times a day and the backend caches for an hour.
const POLL_INTERVAL_MS = 3_600_000

// Everything Quiver has (~300 rows) comes back in one call so the widget can
// filter by member and side without another request.
const LIMIT = 300

export function useCongressTrades() {
  const [data, setData] = useState<CongressTrades | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    async function load() {
      try {
        const res = await fetch(`/api/stocks/congress-trades?limit=${LIMIT}`, { signal: controller.signal })
        if (!res.ok) throw new Error('Failed to fetch congress trades')
        const payload = (await res.json()) as Partial<CongressTrades> | null
        const summary = payload?.summary
        setData({
          trades: Array.isArray(payload?.trades) ? payload.trades : [],
          summary: {
            trades: summary?.trades ?? 0,
            buys: summary?.buys ?? 0,
            sells: summary?.sells ?? 0,
            most_bought: Array.isArray(summary?.most_bought) ? summary.most_bought : [],
            most_sold: Array.isArray(summary?.most_sold) ? summary.most_sold : [],
            politicians: Array.isArray(summary?.politicians) ? summary.politicians : [],
          },
          filter: payload?.filter ?? { politician: null, stocks_only: true },
          as_of: payload?.as_of ?? null,
          source: String(payload?.source ?? 'quiver'),
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
