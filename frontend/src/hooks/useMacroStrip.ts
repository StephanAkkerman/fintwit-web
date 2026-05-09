import { useEffect, useState } from 'react'
import type { MacroTickerItem } from '../types'

export function useMacroStrip() {
  const [data, setData] = useState<MacroTickerItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(false)
    fetch('/api/overview/macro-strip', { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error('macro-strip'); return r.json() })
      .then(p => setData(Array.isArray(p) ? p : []))
      .catch(e => { if (e.name !== 'AbortError') setError(true) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [])

  return { data, loading, error }
}
