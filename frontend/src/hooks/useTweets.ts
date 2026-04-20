import { useEffect, useMemo, useRef, useState } from 'react'
import type { Tweet } from '../types'

/**
 * Loads initial tweets from /api/posts using a time window (24h by default), supports pagination,
 * and then subscribes to /api/stream via SSE.
 * Dedups by tweet.id and keeps up to `maxItems` in memory.
 */
export function useTweets(
  apiBase = '',
  maxItems = 2000,
  pageSize = 200,
  optionsOnly = false,
  sinceHours: number | null = 24
) {
  const [tweets, setTweets] = useState<Tweet[]>([])
  const [hasMore, setHasMore] = useState(true)
  const [isInitialLoading, setIsInitialLoading] = useState(false)
  const [isLoadingOlder, setIsLoadingOlder] = useState(false)
  const [lastLoadDurationMs, setLastLoadDurationMs] = useState<number | null>(null)
  const [lastLoadedCount, setLastLoadedCount] = useState(0)
  const ids = useRef<Set<number>>(new Set())
  const loadingOlderRef = useRef(false)

  const buildPostsQuery = (beforeId?: number) => {
    const params = new URLSearchParams()
    params.set('limit', String(pageSize))
    if (beforeId !== undefined) params.set('before_id', String(beforeId))
    if (sinceHours !== null) params.set('since_hours', String(sinceHours))
    if (optionsOnly) params.set('options_only', 'true')
    return params.toString()
  }

  // initial load
  useEffect(() => {
    let cancelled = false
    setIsInitialLoading(true)
    ;(async () => {
      const startedAt = globalThis.performance?.now?.() ?? Date.now()
      try {
        const query = buildPostsQuery()
        const r = await fetch(`${apiBase}/api/posts?${query}`, {
          credentials: 'include',
        })
        const data: Tweet[] = await r.json()
        if (cancelled) return
        const endedAt = globalThis.performance?.now?.() ?? Date.now()
        ids.current = new Set(data.map((t) => t.id))
        setTweets(data)
        setLastLoadedCount(data.length)
        setLastLoadDurationMs(Math.max(0, Math.round(endedAt - startedAt)))
        setHasMore(data.length === pageSize)
      } catch (e) {
        if (cancelled) return
        console.error('initial load failed', e)
        setLastLoadedCount(0)
        setHasMore(false)
      } finally {
        if (!cancelled) {
          setIsInitialLoading(false)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [apiBase, pageSize, optionsOnly, sinceHours])

  const loadOlder = async () => {
    if (loadingOlderRef.current || !hasMore) return

    const oldest = tweets[tweets.length - 1]
    if (!oldest?.id) {
      setHasMore(false)
      return
    }

    loadingOlderRef.current = true
    setIsLoadingOlder(true)

    try {
      const query = buildPostsQuery(oldest.id)
      const r = await fetch(`${apiBase}/api/posts?${query}`, {
        credentials: 'include',
      })
      const older: Tweet[] = await r.json()

      setTweets((prev) => {
        const seen = new Set(prev.map((t) => t.id))
        const fresh = older.filter((t) => !seen.has(t.id))
        const next = [...prev, ...fresh]
        ids.current = new Set(next.map((t) => t.id))
        return next.slice(0, maxItems)
      })

      setHasMore(older.length === pageSize)
    } catch (e) {
      console.error('older page load failed', e)
      setHasMore(false)
    } finally {
      loadingOlderRef.current = false
      setIsLoadingOlder(false)
    }
  }

  // live updates
  useEffect(() => {
    const optionsQuery = optionsOnly ? '?options_only=true' : ''
    const es = new EventSource(`${apiBase}/api/stream${optionsQuery}`, { withCredentials: true })
    es.onmessage = (ev) => {
      try {
        const t: Tweet = JSON.parse(ev.data)
        setTweets((prev) => {
          const idx = prev.findIndex((item) => item.id === t.id)

          if (idx === -1) {
            ids.current.add(t.id)
            return [t, ...prev].slice(0, maxItems)
          }

          const next = [...prev]
          next[idx] = { ...next[idx], ...t }
          return next
        })
      } catch (e) {
        console.error('error parsing event', e)
      }
    }
    es.onerror = () => {
      // Default EventSource will auto-reconnect; you could also show a small banner.
    }
    return () => es.close()
  }, [apiBase, maxItems, optionsOnly])

  return useMemo(
    () => ({
      tweets,
      hasMore,
      isInitialLoading,
      isLoadingOlder,
      loadOlder,
      lastLoadDurationMs,
      lastLoadedCount,
    }),
    [tweets, hasMore, isInitialLoading, isLoadingOlder, lastLoadDurationMs, lastLoadedCount]
  )
}
