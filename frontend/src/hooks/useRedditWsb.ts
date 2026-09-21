import { useEffect, useState } from 'react'
import type { RedditPost } from '../types'

export function useRedditWsb(limit = 8, subreddit = 'wallstreetbets') {
  const [data, setData] = useState<RedditPost[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(false)

    const params = new URLSearchParams({ limit: String(limit), subreddit })
    fetch(`/api/reddit/wsb?${params}`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch Reddit WSB data')
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
  }, [limit, subreddit])

  return { data, loading, error }
}
