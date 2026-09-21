import { useEffect, useState } from 'react'
import type { RedditCategories } from '../types'

const EMPTY: RedditCategories = { available: false, default: [], categories: {} }

/** The subreddit catalogue behind the Reddit section's subreddit filter. */
export function useRedditCategories() {
  const [data, setData] = useState<RedditCategories>(EMPTY)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()

    fetch('/api/reddit/categories', { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch Reddit categories')
        return res.json()
      })
      .then((payload) => {
        setData({ ...EMPTY, ...(payload ?? {}) })
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [])

  return { data, loading }
}
