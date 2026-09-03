import { useEffect, useState } from 'react'
import type { EarningsCalendar } from '../types'

const EMPTY: EarningsCalendar = { start_date: '', end_date: '', days: [], source: 'nasdaq' }

export function useEarningsCalendar(days = 7) {
  const [data, setData] = useState<EarningsCalendar>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(false)

    fetch(`/api/earnings/calendar?days=${days}`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch earnings calendar')
        return res.json()
      })
      .then((payload) => {
        setData(payload && Array.isArray(payload.days) ? payload : EMPTY)
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(true)
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [days])

  return { data, loading, error }
}
