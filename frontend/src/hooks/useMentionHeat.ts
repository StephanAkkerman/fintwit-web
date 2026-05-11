import { useEffect, useState } from 'react'
import type { AssetKind, MentionHeatCell } from '../types'

export function useMentionHeat(
  assetKind: AssetKind = 'all',
  windowHours = 24,
  userFilter: string | null = null,
  subscriberOnly = false,
) {
  const [data, setData] = useState<MentionHeatCell[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(false)
    const params = new URLSearchParams({ asset_kind: assetKind, window_hours: String(windowHours) })
    if (userFilter) params.set('user_screen_name', userFilter)
    if (subscriberOnly) params.set('subscriber_only', 'true')
    fetch(`/api/overview/mention-heat?${params}`, { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error('mention-heat'); return r.json() })
      .then(p => setData(Array.isArray(p) ? p : []))
      .catch(e => { if (e.name !== 'AbortError') setError(true) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [assetKind, windowHours, userFilter, subscriberOnly])

  return { data, loading, error }
}
