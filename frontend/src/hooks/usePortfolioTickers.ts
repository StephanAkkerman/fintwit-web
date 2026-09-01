import { useCallback, useEffect, useState } from 'react'
import type { PortfolioPosition } from '../types'

const POLL_INTERVAL_MS = 300_000
const RECENT_DAYS = 30
const RECENT_WINDOW_MS = RECENT_DAYS * 24 * 60 * 60 * 1000

export type PortfolioTickerStatus = 'active' | 'recent'
export type PortfolioTickerLookup = (symbol: string) => PortfolioTickerStatus | null

function statusMapFromPositions(positions: PortfolioPosition[]): Map<string, PortfolioTickerStatus> {
  const cutoff = Date.now() - RECENT_WINDOW_MS
  const statusBySymbol = new Map<string, PortfolioTickerStatus>()

  for (const position of positions) {
    const symbol = position.symbol?.trim().toUpperCase()
    if (!symbol) continue

    if (position.is_active) {
      statusBySymbol.set(symbol, 'active')
      continue
    }

    if (statusBySymbol.get(symbol) === 'active') continue

    const closedAt = position.updated_at ? Date.parse(position.updated_at) : NaN
    if (!Number.isNaN(closedAt) && closedAt >= cutoff) {
      statusBySymbol.set(symbol, 'recent')
    }
  }

  return statusBySymbol
}

/**
 * Fetches all portfolio positions (active and closed) and exposes a
 * `symbol -> 'active' | 'recent' | null` lookup so post cards can flag
 * tickers that are currently held or were held within the last 30 days.
 */
export function usePortfolioTickers(): PortfolioTickerLookup {
  const [statusBySymbol, setStatusBySymbol] = useState<Map<string, PortfolioTickerStatus>>(
    () => new Map()
  )

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      try {
        const res = await fetch('/api/portfolio/positions')
        if (!res.ok) return
        const positions = (await res.json()) as PortfolioPosition[]
        if (cancelled || !Array.isArray(positions)) return
        setStatusBySymbol(statusMapFromPositions(positions))
      } catch {
        // Non-fatal; badges simply stay hidden until the next poll succeeds.
      }
    }

    void load()
    const id = setInterval(() => void load(), POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  return useCallback(
    (symbol: string) => statusBySymbol.get(symbol.trim().toUpperCase()) ?? null,
    [statusBySymbol]
  )
}
