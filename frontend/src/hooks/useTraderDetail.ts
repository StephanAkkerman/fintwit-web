import { useEffect, useState } from 'react'
import type { TraderCallHorizon, TraderDetail } from '../types'

/**
 * One trader's profile: per-horizon accuracy, per-ticker breakdown graded at
 * `horizonDays`, and their recent calls. Idle (no request) while
 * `screenName` is null.
 */
export function useTraderDetail(screenName: string | null, horizonDays: TraderCallHorizon) {
  const [data, setData] = useState<TraderDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!screenName) {
      setData(null)
      setLoading(false)
      setError(false)
      return
    }

    const controller = new AbortController()
    setLoading(true)
    setError(false)

    fetch(
      `/api/traders/user/${encodeURIComponent(screenName)}?horizon_days=${horizonDays}&limit=100`,
      { signal: controller.signal }
    )
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch trader detail')
        return res.json()
      })
      .then((payload: TraderDetail) => {
        // Guard against a partial/unexpected payload (e.g. an older backend
        // without the per-ticker breakdown) rather than throwing in render.
        setData({
          ...payload,
          horizons: Array.isArray(payload?.horizons) ? payload.horizons : [],
          tickers: Array.isArray(payload?.tickers) ? payload.tickers : [],
          recent_calls: Array.isArray(payload?.recent_calls) ? payload.recent_calls : [],
        })
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(true)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [screenName, horizonDays])

  return { data, loading, error }
}
