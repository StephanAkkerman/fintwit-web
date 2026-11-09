import { useCallback, useEffect, useRef, useState } from 'react'
import type { BacktestStatus } from '../types'

const POLL_MS = 5000

/**
 * The advisor backtest. The backend runs it in the background, so while it
 * reports `running` this polls until the result is ready.
 */
export function useBacktest() {
  const [data, setData] = useState<BacktestStatus | null>(null)
  const [failed, setFailed] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const alive = useRef(true)

  const load = useCallback(async (refresh = false) => {
    if (timer.current) clearTimeout(timer.current)
    try {
      const res = await fetch(`/api/advisor/backtest${refresh ? '?refresh=true' : ''}`)
      if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
      const body = (await res.json()) as BacktestStatus
      if (!alive.current) return
      setData(body)
      setFailed(false)
      if (body?.status === 'running') {
        timer.current = setTimeout(() => void load(), POLL_MS)
      }
    } catch {
      if (alive.current) setFailed(true)
    }
  }, [])

  useEffect(() => {
    alive.current = true
    void load()
    return () => {
      alive.current = false
      if (timer.current) clearTimeout(timer.current)
    }
  }, [load])

  return { data, failed, rerun: () => load(true) }
}
