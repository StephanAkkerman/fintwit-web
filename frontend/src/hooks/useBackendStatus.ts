import { useEffect, useState } from 'react'
import type { BackendStatus } from '../types'

const POLL_INTERVAL_MS = 60_000

/** Polls the backend's uptime, unexpected restarts and peak memory. */
export function useBackendStatus() {
  const [status, setStatus] = useState<BackendStatus | null>(null)

  useEffect(() => {
    let cancelled = false

    const load = () => {
      fetch('/api/backend/status')
        .then((res) => {
          if (!res.ok) throw new Error('backend status fetch failed')
          return res.json() as Promise<BackendStatus>
        })
        .then((payload) => {
          if (!cancelled) setStatus(payload)
        })
        // Clear it: "running since" must not linger while the backend is down.
        .catch(() => {
          if (!cancelled) setStatus(null)
        })
    }

    load()
    const id = setInterval(load, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  return status
}
