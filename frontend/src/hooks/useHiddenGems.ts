import { useEffect, useState } from 'react'
import type { AssetKind, HiddenGemItem } from '../types'

export function useHiddenGems(assetKind: AssetKind = 'all') {
  const [data, setData] = useState<HiddenGemItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(false)
    const params = new URLSearchParams({ asset_kind: assetKind })
    fetch(`/api/overview/hidden-gems?${params}`, { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error('hidden-gems'); return r.json() })
      .then(p => setData(Array.isArray(p) ? p : []))
      .catch(e => { if (e.name !== 'AbortError') setError(true) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [assetKind])

  return { data, loading, error }
}
