import { useEffect, useState } from 'react'
import type { OptionsChainResponse } from '../types'

function emptyChain(symbol: string): OptionsChainResponse {
  return {
    symbol,
    underlying: {},
    expirations: [],
    expiration: '',
    contracts: [],
    source: 'yfinance',
  }
}

function normalizePayload(payload: unknown, symbol: string): OptionsChainResponse {
  if (!payload || typeof payload !== 'object') return emptyChain(symbol)

  const candidate = payload as Partial<OptionsChainResponse>
  if (!Array.isArray(candidate.contracts)) return emptyChain(symbol)

  return {
    symbol: String(candidate.symbol ?? symbol),
    underlying: candidate.underlying && typeof candidate.underlying === 'object' ? candidate.underlying : {},
    expirations: Array.isArray(candidate.expirations) ? candidate.expirations : [],
    expiration: String(candidate.expiration ?? ''),
    contracts: candidate.contracts,
    source: String(candidate.source ?? 'yfinance'),
  }
}

export function useOptionsChain(symbol: string, expiration?: string) {
  const [data, setData] = useState<OptionsChainResponse>(() => emptyChain(symbol))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const trimmed = symbol.trim()
    if (!trimmed) {
      setData(emptyChain(symbol))
      setLoading(false)
      setError(false)
      return
    }

    const controller = new AbortController()
    setLoading(true)
    setError(false)

    const params = new URLSearchParams({ symbol: trimmed })
    if (expiration) params.set('expiration', expiration)

    fetch(`/api/options/chain?${params.toString()}`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch options chain')
        return res.json()
      })
      .then((payload) => {
        setData(normalizePayload(payload, trimmed))
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(true)
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [symbol, expiration])

  return { data, loading, error }
}
