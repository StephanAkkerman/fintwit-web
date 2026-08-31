import { useCallback, useEffect, useRef, useState } from 'react'
import type { PortfolioHistory, PortfolioHistoryRange } from '../types'

const POLL_INTERVAL_MS = 300_000

export const PORTFOLIO_RANGES: PortfolioHistoryRange[] = [
  '1W',
  '1M',
  '3M',
  '6M',
  'YTD',
  '1Y',
  '5Y',
  'MAX',
]

export function usePortfolioHistory(initialRange: PortfolioHistoryRange = '3M') {
  const [range, setRange] = useState<PortfolioHistoryRange>(initialRange)
  const [history, setHistory] = useState<PortfolioHistory | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Keeps the previous chart on screen while a new range loads instead of
  // collapsing to a skeleton on every switch.
  const hasLoadedRef = useRef(false)

  const load = useCallback(async (nextRange: PortfolioHistoryRange) => {
    if (hasLoadedRef.current) setRefreshing(true)
    else setLoading(true)
    setError(null)

    try {
      const res = await fetch(`/api/portfolio/history?range=${nextRange}`)
      if (!res.ok) throw new Error(`Failed to load portfolio history (${res.status})`)
      setHistory((await res.json()) as PortfolioHistory)
      hasLoadedRef.current = true
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown portfolio history error')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void load(range)
    const id = setInterval(() => void load(range), POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [load, range])

  return {
    history,
    range,
    setRange,
    ranges: PORTFOLIO_RANGES,
    loading,
    refreshing,
    error,
    reload: () => load(range),
  }
}
