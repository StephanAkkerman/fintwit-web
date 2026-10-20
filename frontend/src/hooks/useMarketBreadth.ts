import { useEffect, useState } from 'react'
import type { MarketBreadth, MarketBreadthPoint } from '../types'

// The backend caches the scanner for five minutes.
const POLL_INTERVAL_MS = 300_000
// History gains one point per session, so an hourly refresh is plenty.
const HISTORY_POLL_INTERVAL_MS = 3_600_000
const HISTORY_DAYS = 365

export function useMarketBreadth() {
  const [data, setData] = useState<MarketBreadth | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    async function load() {
      try {
        const res = await fetch('/api/market/breadth', { signal: controller.signal })
        if (!res.ok) throw new Error('Failed to fetch market breadth')
        const payload = (await res.json()) as Partial<MarketBreadth> | null
        setData({
          universes: Array.isArray(payload?.universes) ? payload.universes : [],
          sectors: Array.isArray(payload?.sectors) ? payload.sectors : [],
          session_date: payload?.session_date ?? null,
          as_of: String(payload?.as_of ?? ''),
          source: String(payload?.source ?? 'tradingview'),
        })
        setError(false)
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return
        setError(true)
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }

    void load()
    const id = setInterval(() => void load(), POLL_INTERVAL_MS)
    return () => {
      controller.abort()
      clearInterval(id)
    }
  }, [])

  return { data, loading, error }
}

export function useMarketBreadthHistory(universe: string) {
  const [points, setPoints] = useState<MarketBreadthPoint[]>([])

  useEffect(() => {
    const controller = new AbortController()

    async function load() {
      try {
        const res = await fetch(
          `/api/market/breadth/history?universe=${encodeURIComponent(universe)}&days=${HISTORY_DAYS}`,
          { signal: controller.signal },
        )
        if (!res.ok) throw new Error('Failed to fetch market breadth history')
        const payload = (await res.json()) as { points?: unknown } | null
        setPoints(Array.isArray(payload?.points) ? (payload.points as MarketBreadthPoint[]) : [])
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return
        setPoints([])
      }
    }

    void load()
    const id = setInterval(() => void load(), HISTORY_POLL_INTERVAL_MS)
    return () => {
      controller.abort()
      clearInterval(id)
    }
  }, [universe])

  return points
}
