import { useEffect, useRef, useState } from 'react'
import type { SignaLiveSignal } from '../types'

/** Poll cadence for the live feed. The upstream feed refreshes often, but a
 *  5-minute pull keeps the section fresh without hammering the API. */
export const SIGNA_LIVE_FEED_REFRESH_MS = 5 * 60 * 1000

export function useSignaLiveFeed(limit = 1500, refreshMs = SIGNA_LIVE_FEED_REFRESH_MS) {
  const [data, setData] = useState<SignaLiveSignal[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<number | null>(null)
  // Keep the latest data around so a background refresh doesn't flash a spinner.
  const hasLoadedRef = useRef(false)

  useEffect(() => {
    let cancelled = false

    async function load(controller: AbortController) {
      if (!hasLoadedRef.current) setLoading(true)
      try {
        const res = await fetch(`/api/signa/live-feed?limit=${limit}`, {
          signal: controller.signal,
        })
        if (!res.ok) throw new Error('Failed to fetch Signa live feed')
        const payload = await res.json()
        if (cancelled) return
        setData(Array.isArray(payload) ? payload : [])
        setError(false)
        setLastUpdated(Date.now())
        hasLoadedRef.current = true
      } catch (err) {
        if ((err as Error).name === 'AbortError' || cancelled) return
        setError(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    let controller = new AbortController()
    load(controller)

    const id = window.setInterval(() => {
      controller.abort()
      controller = new AbortController()
      load(controller)
    }, refreshMs)

    return () => {
      cancelled = true
      controller.abort()
      window.clearInterval(id)
    }
  }, [limit, refreshMs])

  return { data, loading, error, lastUpdated }
}
