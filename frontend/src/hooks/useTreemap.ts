import { useEffect, useState } from 'react'
import type { TreemapData } from '../types'

export function useTreemap() {
  const [data, setData] = useState<TreemapData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let isMounted = true

    fetch('/api/treemap')
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch treemap data')
        return res.json()
      })
      .then((d) => {
        if (isMounted) {
          setData(d)
          setLoading(false)
        }
      })
      .catch(() => {
        if (isMounted) {
          setError(true)
          setLoading(false)
        }
      })

    return () => {
      isMounted = false
    }
  }, [])

  return { data, loading, error }
}
