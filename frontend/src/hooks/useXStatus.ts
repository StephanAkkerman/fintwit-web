import { useEffect, useState } from 'react'
import type { XStreamStatus } from '../types'

const POLL_INTERVAL_MS = 60_000

/** Polls whether the backend's X timeline stream is configured and authenticated. */
export function useXStatus() {
  const [status, setStatus] = useState<XStreamStatus | null>(null)

  useEffect(() => {
    let cancelled = false

    const load = () => {
      fetch('/api/x/status')
        .then((res) => {
          if (!res.ok) throw new Error('x status fetch failed')
          return res.json() as Promise<XStreamStatus>
        })
        .then((payload) => {
          if (!cancelled) setStatus(payload)
        })
        // A missing status just means no notice; the timeline still renders.
        .catch(() => {})
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
