import { useEffect, useState } from 'react'
import type { SectorPerformance, SectorOverviewResponse, SpyHeatmapDateRange } from '../types'

export function useSectorOverview(range: SpyHeatmapDateRange = 'one_day') {
  const [data, setData] = useState<SectorPerformance[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(false)

    fetch(`/api/spy-heatmap/sectors?date=${range}`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch sector overview')
        return res.json() as Promise<SectorOverviewResponse>
      })
      .then((payload) => {
        setData(Array.isArray(payload?.sectors) ? payload.sectors : [])
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
