import { useEffect, useState } from 'react'
import type { ForexMacroSnapshot } from '../types'

export function useForexMacroSnapshot() {
  const [data, setData] = useState<ForexMacroSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(false)

    fetch('/api/forex/macro', { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch macro snapshot')
        return res.json()
      })
      .then((payload) => {
        setData(payload as ForexMacroSnapshot)
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