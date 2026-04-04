import { useEffect, useState } from 'react'
import type { TreemapData } from '../types'

export function useTreemap() {
  const [data, setData] = useState<TreemapData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    fetch('/api/treemap', { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch treemap data')
        return res.json()
      })
      .then((d) => {
        setData(d)
        setLoading(false)
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(true)
        setLoading(false)
      })

    return () => controller.abort()
  }, [])

  return { data, loading, error }
}
