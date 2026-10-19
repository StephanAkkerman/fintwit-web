import { useEffect, useState } from 'react'
import type { InsiderTrades } from '../types'

// Form 4s trickle in through the day and the backend caches for 30 minutes.
const POLL_INTERVAL_MS = 1_800_000

// Purchases are rare, so every one in the window is fetched; sales are many
// times more common and mostly routine, so only the newest are. Both come from
// the same cached screener page on the backend.
const BUY_LIMIT = 1000
const SELL_LIMIT = 300

export function useInsiderTrades(days = 30) {
  const [data, setData] = useState<InsiderTrades | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    async function load() {
      try {
        const [buys, sells] = await Promise.all(
          [`side=buy&limit=${BUY_LIMIT}`, `side=sell&limit=${SELL_LIMIT}`].map(async (query) => {
            const res = await fetch(`/api/stocks/insider-trades?days=${days}&${query}`, {
              signal: controller.signal,
            })
            if (!res.ok) throw new Error('Failed to fetch insider trades')
            return (await res.json()) as Partial<InsiderTrades> | null
          }),
        )
        const payload = buys
        const summary = payload?.summary
        const sideOf = (part: Partial<InsiderTrades> | null, side: 'buy' | 'sell') =>
          (Array.isArray(part?.trades) ? part.trades : []).filter((trade) => trade.side === side)
        const trades = [...sideOf(buys, 'buy'), ...sideOf(sells, 'sell')]
          .sort((a, b) => (b.filed_at ?? '').localeCompare(a.filed_at ?? ''))
        setData({
          trades,
          summary: {
            buys: summary?.buys ?? 0,
            sells: summary?.sells ?? 0,
            buy_value: summary?.buy_value ?? 0,
            sell_value: summary?.sell_value ?? 0,
            buy_share_pct: summary?.buy_share_pct ?? null,
            cluster_buys: Array.isArray(summary?.cluster_buys) ? summary.cluster_buys : [],
            top_buys: Array.isArray(summary?.top_buys) ? summary.top_buys : [],
            top_sells: Array.isArray(summary?.top_sells) ? summary.top_sells : [],
          },
          filter: payload?.filter ?? { days, min_value: 25_000, ticker: null, side: null },
          as_of: payload?.as_of ?? null,
          source: String(payload?.source ?? 'openinsider'),
        })
        setError(false)
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return
        setError(true)
      } finally {
        setLoading(false)
      }
    }

    void load()
    const id = setInterval(() => void load(), POLL_INTERVAL_MS)
    return () => {
      controller.abort()
      clearInterval(id)
    }
  }, [days])

  return { data, loading, error }
}
