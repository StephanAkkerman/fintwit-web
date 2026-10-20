import { useEffect, useState } from 'react'
import type { WorldIndices } from '../types'

// Matches the backend's 5-minute cache.
const POLL_INTERVAL_MS = 300_000

export function useWorldIndices() {
  const [data, setData] = useState<WorldIndices | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    async function load() {
      try {
        const res = await fetch('/api/market/world-indices', { signal: controller.signal })
        if (!res.ok) throw new Error('Failed to fetch world indices')
        const payload = (await res.json()) as Partial<WorldIndices> | null
        setData({
          as_of: String(payload?.as_of ?? ''),
          regions: Array.isArray(payload?.regions) ? payload.regions : [],
          semis: payload?.semis ?? null,
          source: String(payload?.source ?? ''),
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
