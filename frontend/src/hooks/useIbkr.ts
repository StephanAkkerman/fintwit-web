import { useCallback, useEffect, useState } from 'react'
import type {
  IbkrAccountSummary,
  IbkrPosition,
  IbkrStatus,
  IbkrTrade,
} from '../types'

const POLL_INTERVAL_MS = 60_000

export function useIbkr() {
  const [status, setStatus] = useState<IbkrStatus | null>(null)
  const [positions, setPositions] = useState<IbkrPosition[]>([])
  const [trades, setTrades] = useState<IbkrTrade[]>([])
  const [account, setAccount] = useState<IbkrAccountSummary>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [statusRes, positionsRes, tradesRes, accountRes] = await Promise.all([
        fetch('/api/ibkr/status'),
        fetch('/api/ibkr/positions'),
        fetch('/api/ibkr/trades?limit=50'),
        fetch('/api/ibkr/account'),
      ])

      if (!statusRes.ok || !positionsRes.ok || !tradesRes.ok || !accountRes.ok) {
        throw new Error('Failed to load IBKR data')
      }

      setStatus((await statusRes.json()) as IbkrStatus)
      setPositions((await positionsRes.json()) as IbkrPosition[])
      setTrades((await tradesRes.json()) as IbkrTrade[])
      setAccount((await accountRes.json()) as IbkrAccountSummary)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown IBKR error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    const id = setInterval(() => void load(), POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [load])

  return { status, positions, trades, account, loading, error, reload: load }
}
