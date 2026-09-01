import { useCallback, useEffect, useState } from 'react'
import type { PortfolioInsights } from '../types'

const POLL_INTERVAL_MS = 300_000

export function usePortfolioInsights() {
  const [insights, setInsights] = useState<PortfolioInsights | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const res = await fetch('/api/portfolio/insights')
      if (!res.ok) throw new Error(`Failed to load portfolio insights (${res.status})`)
      setInsights((await res.json()) as PortfolioInsights)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown portfolio insights error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    const id = setInterval(() => void load(), POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [load])

  return { insights, loading, error, reload: load }
}
