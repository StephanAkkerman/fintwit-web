import { useCallback, useEffect, useState } from 'react'
import type { FxRates } from '../types'

const POLL_INTERVAL_MS = 300_000

export function useFxRates() {
  const [fxRates, setFxRates] = useState<FxRates | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const res = await fetch('/api/fx/rates')
      if (!res.ok) throw new Error(`Failed to load FX rates (${res.status})`)
      setFxRates((await res.json()) as FxRates)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown FX rates error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    const id = setInterval(() => void load(), POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [load])

  return { fxRates, loading, error, reload: load }
}
