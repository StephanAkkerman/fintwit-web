import { useEffect, useMemo, useRef, useState } from 'react'
import type { Tweet } from '../types'

/**
 * Loads initial tweets from /api/posts and then subscribes to /api/stream via SSE.
 * Dedups by tweet.id and keeps up to `maxItems` in memory.
 */
export function useTweets(apiBase = '', maxItems = 500) {
  const [tweets, setTweets] = useState<Tweet[]>([])
  const ids = useRef<Set<number>>(new Set())

  // initial load
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const r = await fetch(`${apiBase}/api/posts`, { credentials: 'include' })
        const data: Tweet[] = await r.json()
        if (cancelled) return
        ids.current = new Set(data.map((t) => t.id))
        setTweets(data)
      } catch (e) {
        console.error('initial load failed', e)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [apiBase])

  // live updates
  useEffect(() => {
    const es = new EventSource(`${apiBase}/api/stream`, { withCredentials: true })
    es.onmessage = (ev) => {
      try {
        const t: Tweet = JSON.parse(ev.data)
        if (!ids.current.has(t.id)) {
          ids.current.add(t.id)
          setTweets((prev) => [t, ...prev].slice(0, maxItems))
        }
      } catch (e) {
        console.error('error parsing event', e)
      }
    }
    es.onerror = () => {
      // Default EventSource will auto-reconnect; you could also show a small banner.
    }
    return () => es.close()
  }, [apiBase, maxItems])

  return useMemo(() => ({ tweets }), [tweets])
}