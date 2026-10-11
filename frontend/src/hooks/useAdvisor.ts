import { useCallback, useEffect, useState } from 'react'
import type { AdvisorCall, AdvisorScorecard, AdvisorStrategy, AdvisorStrategyDraft } from '../types'

const EMPTY_STRATEGY: AdvisorStrategy = {
  rules: '',
  watchlist: [],
  available_cash: null,
  cash_currency: null,
  updated_at: null,
}

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal })
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
  return (await res.json()) as T
}

export function useAdvisor() {
  const [strategy, setStrategy] = useState<AdvisorStrategy>(EMPTY_STRATEGY)
  const [calls, setCalls] = useState<AdvisorCall[]>([])
  const [scorecard, setScorecard] = useState<AdvisorScorecard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true)
    setError(false)
    try {
      const [s, c, card] = await Promise.all([
        getJson<AdvisorStrategy>('/api/advisor/strategy', signal),
        getJson<AdvisorCall[]>('/api/advisor/calls?limit=100', signal),
        getJson<AdvisorScorecard>('/api/advisor/scorecard', signal),
      ])
      setStrategy({ ...EMPTY_STRATEGY, ...s, watchlist: Array.isArray(s?.watchlist) ? s.watchlist : [] })
      setCalls(Array.isArray(c) ? c : [])
      setScorecard(card && typeof card === 'object' && 'horizons' in card ? card : null)
    } catch (err) {
      if ((err as Error).name === 'AbortError') return
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  const saveStrategy = useCallback(async (draft: AdvisorStrategyDraft) => {
    const res = await fetch('/api/advisor/strategy', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(draft),
    })
    if (!res.ok) throw new Error(`Saving failed with status ${res.status}`)
    const saved = (await res.json()) as AdvisorStrategy
    setStrategy(saved)
    return saved
  }, [])

  return { strategy, calls, scorecard, loading, error, saveStrategy, reload: load }
}
