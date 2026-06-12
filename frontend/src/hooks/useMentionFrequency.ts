import { useCallback, useEffect, useRef, useState } from 'react'
import type { MentionFrequency, MentionFrequencyResponse, Tweet } from '../types'

const TTL_MS = 5 * 60 * 1000 // matches the macro-strip cache window
const DEBOUNCE_MS = 400
const MAX_AUTHORS_PER_BATCH = 300 // server caps the request list at 300

type CacheEntry = { value: MentionFrequency; ts: number }

/** Author + the uppercase tickers shown for one tweet, or null if none apply. */
function tweetPairs(t: Tweet): { author: string; tickers: string[] } | null {
  const author = (t.user_screen_name || '').trim()
  if (!author) return null

  const tickers = new Set<string>()
  for (const x of t.tickers ?? []) if (x) tickers.add(x.toUpperCase())
  for (const a of t.assets ?? []) if (a?.symbol) tickers.add(a.symbol.toUpperCase())
  for (const m of (t.text ?? '').matchAll(/(?<!\w)\$([a-z][a-z0-9]{0,9})\b/gi)) {
    tickers.add(m[1].toUpperCase())
  }

  if (tickers.size === 0) return null
  return { author, tickers: [...tickers] }
}

const cacheKey = (author: string, ticker: string) =>
  `${author.toLowerCase()}|${ticker.toUpperCase()}`

/**
 * Fetches per-(author, ticker) mention-frequency stats for the visible tweets
 * in one batched POST, caches them with a 5-minute TTL, and exposes a
 * `lookup(author, ticker)` for `TweetCard`. Only missing/stale pairs are
 * requested, so streaming new tweets fetches only their new pairs.
 */
export function useMentionFrequency(tweets: Tweet[], apiBase = '') {
  const cache = useRef<Map<string, CacheEntry>>(new Map())
  const [version, setVersion] = useState(0)

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()

    const timer = setTimeout(() => {
      const now = Date.now()

      // Group the stale/missing tickers we need by author.
      const byAuthor = new Map<string, Set<string>>()
      for (const t of tweets) {
        const pair = tweetPairs(t)
        if (!pair) continue
        for (const ticker of pair.tickers) {
          const entry = cache.current.get(cacheKey(pair.author, ticker))
          if (entry && now - entry.ts < TTL_MS) continue
          const set = byAuthor.get(pair.author) ?? new Set<string>()
          set.add(ticker)
          byAuthor.set(pair.author, set)
        }
      }

      if (byAuthor.size === 0) return

      const requests = [...byAuthor.entries()]
        .slice(0, MAX_AUTHORS_PER_BATCH)
        .map(([author, tickers]) => ({ author, tickers: [...tickers] }))

      ;(async () => {
        try {
          const r = await fetch(`${apiBase}/api/overview/mention-frequency`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ requests }),
            signal: controller.signal,
          })
          if (!r.ok) return
          const data = (await r.json()) as MentionFrequencyResponse
          if (cancelled) return

          const ts = Date.now()
          for (const { author, tickers } of requests) {
            const personalForAuthor = data.personal?.[author] ?? {}
            for (const ticker of tickers) {
              cache.current.set(cacheKey(author, ticker), {
                value: {
                  personal: personalForAuthor[ticker] ?? null,
                  global: data.global?.[ticker] ?? null,
                },
                ts,
              })
            }
          }
          setVersion((v) => v + 1)
        } catch {
          // Network/abort errors are non-fatal; the strip just stays hidden.
        }
      })()
    }, DEBOUNCE_MS)

    return () => {
      cancelled = true
      controller.abort()
      clearTimeout(timer)
    }
  }, [tweets, apiBase])

  const lookup = useCallback(
    (author: string, ticker: string): MentionFrequency | undefined => {
      void version // re-create lookup when the cache changes
      return cache.current.get(cacheKey(author, ticker))?.value
    },
    [version]
  )

  return lookup
}

export type MentionLookup = ReturnType<typeof useMentionFrequency>
