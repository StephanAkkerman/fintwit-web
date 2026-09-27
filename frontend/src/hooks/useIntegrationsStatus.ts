import { useEffect, useState } from 'react'

type IntegrationsState = {
  signa: boolean | null
  reddit: boolean | null
}

const UNKNOWN: IntegrationsState = { signa: null, reddit: null }

/**
 * Whether user-supplied third-party integrations (Signa, Reddit) are
 * configured on this deployment. `null` means "not yet known" — the caller
 * should treat that the same as configured to avoid hiding a section only to
 * show it a moment later once the request resolves.
 */
export function useIntegrationsStatus() {
  const [status, setStatus] = useState<IntegrationsState>(UNKNOWN)

  useEffect(() => {
    const controller = new AbortController()

    fetch('/api/integrations/status', { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : null))
      .then((payload: Partial<Record<'signa' | 'reddit', boolean>> | null) => {
        if (!payload) return
        setStatus({
          signa: typeof payload.signa === 'boolean' ? payload.signa : null,
          reddit: typeof payload.reddit === 'boolean' ? payload.reddit : null,
        })
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
      })

    return () => controller.abort()
  }, [])

  return status
}
