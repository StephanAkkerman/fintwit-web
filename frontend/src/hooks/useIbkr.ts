import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  IbkrAccountSummary,
  IbkrPosition,
  IbkrStatus,
  IbkrTrade,
} from '../types'

const POLL_INTERVAL_MS = 60_000
// While a re-login waits for the 2FA approval, poll faster so the panel turns
// green soon after the prompt is approved.
const RELOGIN_POLL_INTERVAL_MS = 10_000

export function useIbkr() {
  const [status, setStatus] = useState<IbkrStatus | null>(null)
  const [positions, setPositions] = useState<IbkrPosition[]>([])
  const [trades, setTrades] = useState<IbkrTrade[]>([])
  const [account, setAccount] = useState<IbkrAccountSummary>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Only the first load shows the loading state; polls refresh in place
  // instead of blanking the tables every interval.
  const loaded = useRef(false)
  const load = useCallback(async () => {
    setLoading(!loaded.current)
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
      loaded.current = true
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown IBKR error')
    } finally {
      setLoading(false)
    }
  }, [])

  const restarting = status?.state === 'restarting'
  useEffect(() => {
    void load()
    const id = setInterval(
      () => void load(),
      restarting ? RELOGIN_POLL_INTERVAL_MS : POLL_INTERVAL_MS,
    )
    return () => clearInterval(id)
  }, [load, restarting])

  const [reloginError, setReloginError] = useState<string | null>(null)
  const relogin = useCallback(async () => {
    setReloginError(null)
    try {
      const res = await fetch('/api/ibkr/relogin', { method: 'POST' })
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { detail?: string } | null
        throw new Error(body?.detail ?? `Re-login failed (${res.status})`)
      }
    } catch (e) {
      setReloginError(e instanceof Error ? e.message : 'Re-login failed')
    }
    await load()
  }, [load])

  return {
    status,
    positions,
    trades,
    account,
    loading,
    error,
    reload: load,
    relogin,
    reloginError,
  }
}
