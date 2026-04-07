import { useEffect, useMemo, useRef, useState } from 'react'
import type { Tweet } from '../types'

/**
 * Loads initial tweets from /api/posts (200 by default), supports pagination,
 * and then subscribes to /api/stream via SSE.
 * Dedups by tweet.id and keeps up to `maxItems` in memory.
 */
export function useTweets(apiBase = '', maxItems = 2000, pageSize = 200) {
  const [tweets, setTweets] = useState<Tweet[]>([])
  const [hasMore, setHasMore] = useState(true)
  const [isLoadingOlder, setIsLoadingOlder] = useState(false)
  const ids = useRef<Set<number>>(new Set())
  const loadingOlderRef = useRef(false)

  // initial load
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const r = await fetch(`${apiBase}/api/posts?limit=${pageSize}`, {
          credentials: 'include',
        })
        const data: Tweet[] = await r.json()
        if (cancelled) return
        ids.current = new Set(data.map((t) => t.id))
        setTweets(data)
        setHasMore(data.length === pageSize)
      } catch (e) {
        console.error('initial load failed', e)
        setHasMore(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [apiBase, pageSize])

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
      const r = await fetch(`${apiBase}/api/posts?limit=${pageSize}&before_id=${oldest.id}`, {
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
    const es = new EventSource(`${apiBase}/api/stream`, { withCredentials: true })
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
  }, [apiBase, maxItems])

  return useMemo(
    () => ({ tweets, hasMore, isLoadingOlder, loadOlder }),
    [tweets, hasMore, isLoadingOlder]
  )
}
