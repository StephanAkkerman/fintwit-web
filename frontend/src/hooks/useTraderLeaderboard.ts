import { useEffect, useState } from 'react'
import type { TraderCallHorizon, TraderLeaderboardEntry } from '../types'

export function useTraderLeaderboard(horizonDays: TraderCallHorizon, minCalls = 5) {
  const [data, setData] = useState<TraderLeaderboardEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(false)

    fetch(`/api/traders/leaderboard?horizon_days=${horizonDays}&min_calls=${minCalls}`, {
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch trader leaderboard')
        return res.json()
      })
      .then((payload) => {
        setData(Array.isArray(payload) ? payload : [])
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(true)
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [horizonDays, minCalls])

  return { data, loading, error }
}
