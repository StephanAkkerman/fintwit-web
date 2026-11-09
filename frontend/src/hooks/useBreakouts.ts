import { useEffect, useState } from 'react'
import type { BreakoutHistory, BreakoutScreen } from '../types'

// The screener runs every few hours on weekly bars; an hourly refresh is plenty.
const POLL_INTERVAL_MS = 3_600_000
const HISTORY_DAYS = 180

const EMPTY_HISTORY: BreakoutHistory = {
  days: HISTORY_DAYS,
  summary: { flagged: 0, with_return: 0, avg_return_pct: null, win_rate_pct: null },
  signals: [],
}

export function useBreakouts() {
  const [screen, setScreen] = useState<BreakoutScreen | null>(null)
  const [history, setHistory] = useState<BreakoutHistory>(EMPTY_HISTORY)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    async function load() {
      try {
        const [screenRes, historyRes] = await Promise.all([
          fetch('/api/stocks/breakouts', { signal: controller.signal }),
          fetch(`/api/stocks/breakouts/history?days=${HISTORY_DAYS}`, { signal: controller.signal }),
        ])
        if (!screenRes.ok) throw new Error('Failed to fetch breakouts')
        const payload = (await screenRes.json()) as Partial<BreakoutScreen> | null
        setScreen({
          run: payload?.run ?? null,
          breakouts: Array.isArray(payload?.breakouts) ? payload.breakouts : [],
          watch: Array.isArray(payload?.watch) ? payload.watch : [],
          criteria: payload?.criteria ?? null,
        })
        if (historyRes.ok) {
          const past = (await historyRes.json()) as Partial<BreakoutHistory> | null
          setHistory({
            days: past?.days ?? HISTORY_DAYS,
            summary: { ...EMPTY_HISTORY.summary, ...(past?.summary ?? {}) },
            signals: Array.isArray(past?.signals) ? past.signals : [],
          })
        }
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

  return { screen, history, loading, error }
}
