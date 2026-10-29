import { useCallback, useEffect, useState } from 'react'
import type {
  AdvisorCall,
  AdvisorRun,
  AdvisorScorecard,
  AdvisorStrategy,
  AdvisorStrategyDraft,
  PaperPortfolio,
} from '../types'

const EMPTY_STRATEGY: AdvisorStrategy = {
  rules: '',
  watchlist: [],
  followed_traders: [],
  feed_markets: ['stocks', 'options'],
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
  const [runs, setRuns] = useState<AdvisorRun[]>([])
  const [scorecard, setScorecard] = useState<AdvisorScorecard | null>(null)
  const [paper, setPaper] = useState<PaperPortfolio[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true)
    setError(false)
    try {
      const [s, c, card, r, p] = await Promise.all([
        getJson<AdvisorStrategy>('/api/advisor/strategy', signal),
        getJson<AdvisorCall[]>('/api/advisor/calls?limit=100', signal),
        getJson<AdvisorScorecard>('/api/advisor/scorecard', signal),
        getJson<AdvisorRun[]>('/api/advisor/runs?limit=10', signal),
        // Prices every open paper position, so it can fail on its own without
        // taking the rest of the page down.
        getJson<{ strategies: PaperPortfolio[] }>('/api/advisor/paper', signal).catch((err: Error) => {
          if (err.name === 'AbortError') throw err
          return null
        }),
      ])
      setStrategy({
        ...EMPTY_STRATEGY,
        ...s,
        watchlist: Array.isArray(s?.watchlist) ? s.watchlist : [],
        followed_traders: Array.isArray(s?.followed_traders) ? s.followed_traders : [],
        feed_markets: Array.isArray(s?.feed_markets) ? s.feed_markets : EMPTY_STRATEGY.feed_markets,
      })
      setCalls(Array.isArray(c) ? c : [])
      setRuns(Array.isArray(r) ? r : [])
      setPaper(Array.isArray(p?.strategies) ? p.strategies : [])
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

  return { strategy, calls, runs, scorecard, paper, loading, error, saveStrategy, reload: load }
}
