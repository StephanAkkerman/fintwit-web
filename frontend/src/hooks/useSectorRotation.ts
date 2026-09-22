import { useEffect, useState } from 'react'
import type { SectorRotationResponse, SectorRotationSeries, SectorRotationTimeframe } from '../types'

export function useSectorRotation(timeframe: SectorRotationTimeframe = 'daily') {
  const [data, setData] = useState<SectorRotationSeries[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(false)

    fetch(`/api/sector-rotation?timeframe=${timeframe}`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch sector rotation')
        return res.json() as Promise<SectorRotationResponse>
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
  }, [timeframe])

  return { data, loading, error }
}
