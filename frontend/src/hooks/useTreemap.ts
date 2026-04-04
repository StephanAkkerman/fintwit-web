import { useEffect, useState } from 'react'
import type { TreemapResponse } from '../types'

export function useTreemap() {
  const [data, setData] = useState<TreemapResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    fetch('/api/treemap')
      .then((res) => {
        if (!res.ok) throw new Error('Network response was not ok')
        return res.json()
      })
      .then((d) => {
        setData(d)
        setLoading(false)
      })
      .catch((e) => {
        setError(e)
        setLoading(false)
      })
  }, [])

  return { data, loading, error }
}
