import { useCallback, useEffect, useRef, useState } from 'react'
import type { TraderCallHorizon, TraderHorizonStat, Tweet } from '../types'

const TTL_MS = 5 * 60 * 1000 // matches useMentionFrequency's cache window
const DEBOUNCE_MS = 400
const MAX_AUTHORS_PER_BATCH = 300 // server caps the request list at 300

type CacheEntry = { value: TraderHorizonStat | null; ts: number }

const cacheKey = (author: string) => author.trim().toLowerCase()

/**
 * Fetches per-author call-accuracy stats for the visible tweets in one
 * batched POST, caches them with a 5-minute TTL, and exposes a
 * `lookup(author)` for the `TraderCredibilityBadge` on each `TweetCard`.
 * Mirrors `useMentionFrequency`'s batching so a feed of many authors still
 * costs one request instead of one per card.
 */
export function useTraderCredibility(
  tweets: Tweet[],
  horizonDays: TraderCallHorizon = 7,
  apiBase = ''
) {
  const cache = useRef<Map<string, CacheEntry>>(new Map())
  const [version, setVersion] = useState(0)

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()

    const timer = setTimeout(() => {
      const now = Date.now()

      const authors = new Set<string>()
      for (const t of tweets) {
        const author = (t.user_screen_name || '').trim()
        if (!author) continue
        const key = cacheKey(author)
        const entry = cache.current.get(key)
        if (entry && now - entry.ts < TTL_MS) continue
        authors.add(author)
      }

      if (authors.size === 0) return

      const screen_names = [...authors].slice(0, MAX_AUTHORS_PER_BATCH)

      ;(async () => {
        try {
          const r = await fetch(`${apiBase}/api/traders/credibility`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ screen_names, horizon_days: horizonDays }),
            signal: controller.signal,
          })
          if (!r.ok) return
          const data = (await r.json()) as Record<string, TraderHorizonStat>
          if (cancelled) return

          const ts = Date.now()
          for (const author of screen_names) {
            cache.current.set(cacheKey(author), {
              value: data[cacheKey(author)] ?? null,
              ts,
            })
          }
          setVersion((v) => v + 1)
        } catch {
          // Network/abort errors are non-fatal; the badge just stays hidden.
        }
      })()
    }, DEBOUNCE_MS)

    return () => {
      cancelled = true
      controller.abort()
      clearTimeout(timer)
    }
  }, [tweets, horizonDays, apiBase])

  const lookup = useCallback(
    (author: string): TraderHorizonStat | undefined => {
      void version // re-create lookup when the cache changes
      return cache.current.get(cacheKey(author))?.value ?? undefined
    },
    [version]
  )

  return lookup
}

export type TraderCredibilityLookup = ReturnType<typeof useTraderCredibility>
