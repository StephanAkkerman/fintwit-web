import { useEffect, useState } from 'react'
import type { SignaBestTrade } from '../types'

export function useSignaBestTrades(limit = 100) {
  const [data, setData] = useState<SignaBestTrade[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(false)

    fetch(`/api/signa/best-trades?limit=${limit}`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch Signa best trades')
        return res.json()
      })
      .then((payload) => {
        setData(Array.isArray(payload) ? payload : [])
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(true)
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [limit])

  return { data, loading, error }
}
