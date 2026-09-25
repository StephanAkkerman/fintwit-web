import { useEffect, useState } from 'react'
import type { AssetKind, TrendSummary, TrendWindow } from '../types'

export function useTrendSummary(
  trendWindow: TrendWindow = '7d',
  assetKind: AssetKind = 'all',
  userFilter: string | null = null,
  subscriberOnly = false,
) {
  const [data, setData] = useState<TrendSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(false)
    const params = new URLSearchParams({ window: trendWindow, asset_kind: assetKind })
    if (userFilter) params.set('user_screen_name', userFilter)
    if (subscriberOnly) params.set('subscriber_only', 'true')
    fetch(`/api/overview/trend-summary?${params}`, { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error('trend-summary'); return r.json() })
      .then(p => {
        // Object-shaped payload: anything else (a list, null) is treated as a
        // failed load rather than read field-by-field during render.
        if (p && typeof p === 'object' && !Array.isArray(p) && Array.isArray(p.buckets) && p.totals) setData(p)
        else setError(true)
      })
      .catch(e => { if (e.name !== 'AbortError') setError(true) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [trendWindow, assetKind, userFilter, subscriberOnly])

  return { data, loading, error }
}
