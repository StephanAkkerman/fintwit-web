import { useState, useEffect } from 'react'
import { AnalystRating } from '../types'

export function useAnalystRatings(stock: string) {
  const [ratings, setRatings] = useState<AnalystRating[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!stock) {
      setRatings([])
      return
    }

    const fetchRatings = async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(`/api/analyze/${stock}`)
        if (!res.ok) {
          if (res.status === 404) {
            throw new Error(`Could not find any data for ${stock}`)
          }
          throw new Error('Failed to fetch analyst ratings')
        }
        const data = await res.json()
        setRatings(data)
      } catch (err: any) {
        setError(err.message || 'An error occurred')
        setRatings([])
      } finally {
        setLoading(false)
      }
    }

    fetchRatings()
  }, [stock])

  return { ratings, loading, error }
}
