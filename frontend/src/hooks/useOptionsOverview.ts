import { useEffect, useState } from 'react'
import type { OptionsOverviewResponse } from '../types'

const EMPTY_OPTIONS_OVERVIEW: OptionsOverviewResponse = {
  symbols: [],
  totals: {
    call_volume: 0,
    put_volume: 0,
    total_volume: 0,
    put_call_ratio: null,
  },
  bullish: [],
  bearish: [],
  most_active_contracts: [],
  source: 'nasdaq',
}

function normalizePayload(payload: unknown): OptionsOverviewResponse {
  if (!payload || typeof payload !== 'object') return EMPTY_OPTIONS_OVERVIEW

  const candidate = payload as Partial<OptionsOverviewResponse>
  if (!Array.isArray(candidate.symbols)) return EMPTY_OPTIONS_OVERVIEW

  return {
    symbols: candidate.symbols,
    totals:
      candidate.totals && typeof candidate.totals === 'object'
        ? {
            call_volume: Number(candidate.totals.call_volume ?? 0),
            put_volume: Number(candidate.totals.put_volume ?? 0),
            total_volume: Number(candidate.totals.total_volume ?? 0),
            put_call_ratio:
              candidate.totals.put_call_ratio == null
                ? null
                : Number(candidate.totals.put_call_ratio),
          }
        : EMPTY_OPTIONS_OVERVIEW.totals,
    bullish: Array.isArray(candidate.bullish) ? candidate.bullish : [],
    bearish: Array.isArray(candidate.bearish) ? candidate.bearish : [],
    most_active_contracts: Array.isArray(candidate.most_active_contracts)
      ? candidate.most_active_contracts
      : [],
    source: String(candidate.source ?? 'nasdaq'),
  }
}

export function useOptionsOverview(symbols: string[] = []) {
  const [data, setData] = useState<OptionsOverviewResponse>(EMPTY_OPTIONS_OVERVIEW)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const symbolsKey = symbols.join(',')

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(false)

    const query = symbolsKey ? `?symbols=${encodeURIComponent(symbolsKey)}` : ''

    fetch(`/api/options/overview${query}`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch options overview')
        return res.json()
      })
      .then((payload) => {
        setData(normalizePayload(payload))
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(true)
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [symbolsKey])

  return { data, loading, error }
}
