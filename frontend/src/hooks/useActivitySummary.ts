import { useEffect, useState } from 'react'
import type { ActivitySummary, AssetKind } from '../types'

export function useActivitySummary(
  assetKind: AssetKind = 'all',
  windowHours = 24,
  userFilter: string | null = null,
  subscriberOnly = false,
) {
  const [data, setData] = useState<ActivitySummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(false)
    const params = new URLSearchParams({
      asset_kind: assetKind,
      window_hours: String(windowHours),
    })
    if (userFilter) params.set('user_screen_name', userFilter)
    if (subscriberOnly) params.set('subscriber_only', 'true')
    fetch(`/api/overview/activity-summary?${params}`, { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error('activity-summary'); return r.json() })
      .then(p => {
        // Object-shaped payload: anything else (a list, null) is treated as a
        // failed load rather than read field-by-field during render.
        if (p && typeof p === 'object' && !Array.isArray(p) && p.tweets) setData(p)
        else setError(true)
      })
      .catch(e => { if (e.name !== 'AbortError') setError(true) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [assetKind, windowHours, userFilter, subscriberOnly])

  return { data, loading, error }
}
