import { useEffect, useState } from 'react'
import type { TechnicalIndicators } from '../types'

export type IndicatorsAssetKind = 'stock' | 'etf' | 'crypto'

// The same ticker shows up on many cards; share one request per symbol.
const cache = new Map<string, Promise<TechnicalIndicators | null>>()

function fetchIndicators(
  symbol: string,
  assetKind: IndicatorsAssetKind,
): Promise<TechnicalIndicators | null> {
  const key = `${assetKind}:${symbol}`
  let pending = cache.get(key)
  if (!pending) {
    const params = new URLSearchParams({ symbols: symbol, asset_kind: assetKind })
    pending = fetch(`/api/research/indicators?${params}`)
      .then((res) => (res.ok ? (res.json() as Promise<Record<string, TechnicalIndicators | null>>) : null))
      .then((data) => data?.[symbol] ?? null)
      .catch(() => null)
    // Drop failures so a later expand can retry.
    pending.then((result) => {
      if (result === null) cache.delete(key)
    })
    cache.set(key, pending)
  }
  return pending
}

export function _resetIndicatorsCacheForTests() {
  cache.clear()
}

/**
 * Daily RSI, MACD, moving-average distance, ATR, ADX and volume for one
 * symbol. Fetches only while `enabled`, so a collapsed panel costs nothing.
 */
export function useTechnicalIndicators(
  symbol: string,
  assetKind: IndicatorsAssetKind,
  enabled: boolean,
) {
  const [data, setData] = useState<TechnicalIndicators | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!enabled || !symbol) return
    let active = true
    setLoading(true)
    setError(false)
    void fetchIndicators(symbol.toUpperCase(), assetKind).then((result) => {
      if (!active) return
      setData(result)
      setError(result === null)
      setLoading(false)
    })
    return () => {
      active = false
    }
  }, [enabled, symbol, assetKind])

  return { data, loading, error }
}
