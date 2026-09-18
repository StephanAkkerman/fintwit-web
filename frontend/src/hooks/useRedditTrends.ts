import { useCallback, useEffect, useState } from 'react'
import type { RedditTrendReport } from '../types'

const EMPTY: RedditTrendReport = {
  available: true,
  captured_at: null,
  subreddits: [],
  tickers: [],
}

/**
 * Latest stored Reddit trend ranking (issue #6).
 *
 * The endpoint serves the last completed worker run, so this is a plain fetch
 * with no polling — a new run only lands every 15 minutes by default.
 */
export function useRedditTrends(limit = 10) {
  const [data, setData] = useState<RedditTrendReport>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const load = useCallback(
    (signal?: AbortSignal) => {
      setLoading(true)
      setError(false)

      return fetch(`/api/reddit/trends?limit=${limit}`, { signal })
        .then((res) => {
          if (!res.ok) throw new Error('Failed to fetch Reddit trends')
          return res.json()
        })
        .then((payload) => {
          setData({ ...EMPTY, ...(payload ?? {}) })
        })
        .catch((err) => {
          if (err.name === 'AbortError') return
          setError(true)
        })
        .finally(() => setLoading(false))
    },
    [limit],
  )

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  return { data, loading, error, refresh: load }
}
