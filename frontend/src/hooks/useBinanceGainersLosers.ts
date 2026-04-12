import { useEffect, useState } from 'react'
import type { BinanceGainersLosers, BinanceMoverItem } from '../types'

const EMPTY_BINANCE_MOVERS: BinanceGainersLosers = {
  gainers: [],
  losers: [],
}

function normalizeMovers(payload: unknown): BinanceGainersLosers {
  if (!payload || typeof payload !== 'object') return EMPTY_BINANCE_MOVERS

  const raw = payload as Partial<BinanceGainersLosers>
  const gainers = Array.isArray(raw.gainers) ? (raw.gainers as BinanceMoverItem[]) : []
  const losers = Array.isArray(raw.losers) ? (raw.losers as BinanceMoverItem[]) : []

  return {
    gainers,
    losers,
  }
}

export function useBinanceGainersLosers() {
  const [data, setData] = useState<BinanceGainersLosers>(EMPTY_BINANCE_MOVERS)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(false)

    fetch('/api/binance/gainers-losers', { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch Binance gainers/losers')
        return res.json()
      })
      .then((payload) => {
        setData(normalizeMovers(payload))
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        setError(true)
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [])

  return { data, loading, error }
}
