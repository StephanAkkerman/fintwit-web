import { useEffect, useRef, useState } from 'react'
import type { GammaExposureHistoryPoint, GammaExposureSnapshot } from '../types'

const POLL_INTERVAL_MS = 300_000

const EMPTY_SNAPSHOT: GammaExposureSnapshot = {
  symbol: 'SPY',
  spot_price: 0,
  net_gex: 0,
  call_gex: 0,
  put_gex: 0,
  flip_point: null,
  regime: 'positive',
  expirations_used: [],
  by_strike: [],
  as_of: '',
  source: 'yfinance-bs-estimate',
}

function normalizeSnapshot(payload: unknown, symbol: string): GammaExposureSnapshot | null {
  if (!payload || typeof payload !== 'object') return null

  const candidate = payload as Partial<GammaExposureSnapshot>
  if (typeof candidate.net_gex !== 'number' || typeof candidate.spot_price !== 'number') {
    return null
  }

  return {
    symbol: String(candidate.symbol ?? symbol),
    spot_price: candidate.spot_price,
    net_gex: candidate.net_gex,
    call_gex: Number(candidate.call_gex ?? 0),
    put_gex: Number(candidate.put_gex ?? 0),
    flip_point: candidate.flip_point == null ? null : Number(candidate.flip_point),
    regime: candidate.regime === 'negative' ? 'negative' : 'positive',
    expirations_used: Array.isArray(candidate.expirations_used)
      ? candidate.expirations_used
      : [],
    by_strike: Array.isArray(candidate.by_strike) ? candidate.by_strike : [],
    as_of: String(candidate.as_of ?? ''),
    source: String(candidate.source ?? 'yfinance-bs-estimate'),
  }
}

function normalizeHistory(payload: unknown): GammaExposureHistoryPoint[] {
  if (!payload || typeof payload !== 'object') return []
  const points = (payload as { points?: unknown }).points
  return Array.isArray(points) ? (points as GammaExposureHistoryPoint[]) : []
}

export function useGammaExposure(symbol = 'SPY', historyDays = 30) {
  const [snapshot, setSnapshot] = useState<GammaExposureSnapshot>(EMPTY_SNAPSHOT)
  const [history, setHistory] = useState<GammaExposureHistoryPoint[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const hasLoadedRef = useRef(false)

  useEffect(() => {
    const controller = new AbortController()

    async function load() {
      if (!hasLoadedRef.current) setLoading(true)

      try {
        const [snapshotRes, historyRes] = await Promise.all([
          fetch(`/api/options/gamma-exposure?symbol=${encodeURIComponent(symbol)}`, {
            signal: controller.signal,
          }),
          fetch(
            `/api/options/gamma-exposure/history?symbol=${encodeURIComponent(symbol)}&days=${historyDays}`,
            { signal: controller.signal },
          ),
        ])

        if (!snapshotRes.ok) throw new Error('Failed to fetch gamma exposure')

        const snapshotPayload = normalizeSnapshot(await snapshotRes.json(), symbol)
        if (snapshotPayload) setSnapshot(snapshotPayload)

        if (historyRes.ok) {
          setHistory(normalizeHistory(await historyRes.json()))
        }

        setError(false)
        hasLoadedRef.current = true
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return
        setError(true)
      } finally {
        setLoading(false)
      }
    }

    void load()
    const id = setInterval(() => void load(), POLL_INTERVAL_MS)
    return () => {
      controller.abort()
      clearInterval(id)
    }
  }, [symbol, historyDays])

  return { snapshot, history, loading, error }
}
