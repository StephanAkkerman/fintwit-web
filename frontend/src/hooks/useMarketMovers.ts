import { useEffect, useState } from 'react'
import type { MarketMoversSnapshot } from '../types'

const POLL_INTERVAL_MS = 5 * 60 * 1000 // 5 minutes

export function useMarketMovers() {
  const [data, setData]       = useState<MarketMoversSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(false)

  useEffect(() => {
    let cancelled = false

    const load = () => {
      const controller = new AbortController()

      fetch('/api/stocks/market-movers', { signal: controller.signal })
        .then((res) => {
          if (!res.ok) throw new Error('market-movers fetch failed')
          return res.json() as Promise<MarketMoversSnapshot>
        })
        .then((payload) => {
          if (cancelled) return
          setData(payload)
          setError(false)
        })
        .catch((err) => {
          if (cancelled || err.name === 'AbortError') return
          setError(true)
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })

      return controller
    }

    const controller = load()
    const id = setInterval(() => load(), POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      controller.abort()
      clearInterval(id)
    }
  }, [])

  return { data, loading, error }
}
