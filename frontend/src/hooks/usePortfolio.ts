import { useCallback, useEffect, useState } from 'react'
import type { PortfolioPosition, PortfolioSummary } from '../types'

type CreatePayload = {
  symbol: string
  quantity: number
  avg_cost: number
  notes?: string
}

export function usePortfolio() {
  const [positions, setPositions] = useState<PortfolioPosition[]>([])
  const [summary, setSummary] = useState<PortfolioSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [positionsRes, summaryRes] = await Promise.all([
        fetch('/api/portfolio/positions'),
        fetch('/api/portfolio/summary'),
      ])

      if (!positionsRes.ok || !summaryRes.ok) {
        throw new Error('Failed to load portfolio data')
      }

      const positionsData = (await positionsRes.json()) as PortfolioPosition[]
      const summaryData = (await summaryRes.json()) as PortfolioSummary

      setPositions(Array.isArray(positionsData) ? positionsData : [])
      setSummary(summaryData)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown portfolio error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const addPosition = useCallback(
    async (payload: CreatePayload) => {
      const res = await fetch('/api/portfolio/positions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(`Failed to add position (${res.status})`)
      await load()
    },
    [load]
  )

  const toggleActive = useCallback(
    async (position: PortfolioPosition) => {
      const res = await fetch(`/api/portfolio/positions/${position.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: !position.is_active }),
      })
      if (!res.ok) throw new Error(`Failed to update position (${res.status})`)
      await load()
    },
    [load]
  )

  const removePosition = useCallback(
    async (positionId: number) => {
      const res = await fetch(`/api/portfolio/positions/${positionId}`, {
        method: 'DELETE',
      })
      if (!res.ok) throw new Error(`Failed to delete position (${res.status})`)
      await load()
    },
    [load]
  )

  return {
    positions,
    summary,
    loading,
    error,
    addPosition,
    toggleActive,
    removePosition,
    reload: load,
  }
}
