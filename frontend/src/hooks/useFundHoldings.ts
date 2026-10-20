import { useEffect, useState } from 'react'
import type { FundHoldings } from '../types'

// 13Fs land once a quarter; the backend rebuilds every few hours.
const POLL_INTERVAL_MS = 3_600_000

export function useFundHoldings() {
  const [data, setData] = useState<FundHoldings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    async function load() {
      try {
        const res = await fetch('/api/stocks/fund-holdings', { signal: controller.signal })
        if (!res.ok) throw new Error('Failed to fetch fund holdings')
        const payload = (await res.json()) as Partial<FundHoldings> | null
        setData({
          funds: Array.isArray(payload?.funds) ? payload.funds : [],
          most_bought: Array.isArray(payload?.most_bought) ? payload.most_bought : [],
          most_sold: Array.isArray(payload?.most_sold) ? payload.most_sold : [],
          most_held: Array.isArray(payload?.most_held) ? payload.most_held : [],
          report_date: payload?.report_date ?? null,
          missing: Array.isArray(payload?.missing) ? payload.missing : [],
          as_of: payload?.as_of ?? null,
          source: String(payload?.source ?? 'sec-13f'),
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
