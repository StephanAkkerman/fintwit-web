import { useEffect, useState } from 'react'
import type { SpyHeatmapDateRange, SpyHeatmapItem } from '../types'

type SpyHeatmapPayload = {
  data?: SpyHeatmapItem[]
}

export function useSpyHeatmap(range: SpyHeatmapDateRange = 'one_day') {
  const [data, setData] = useState<SpyHeatmapItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(false)

    fetch(`/api/spy-heatmap?date=${range}`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch SPY heatmap')
        return res.json() as Promise<SpyHeatmapPayload>
      })
      .then((payload) => {
        setData(Array.isArray(payload?.data) ? payload.data : [])
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(true)
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [range])

  return { data, loading, error }
}
