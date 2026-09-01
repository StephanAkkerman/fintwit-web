import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { usePortfolioTickers } from '../hooks/usePortfolioTickers'
import type { PortfolioPosition } from '../types'

const daysAgo = (days: number): string => new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString()

const makePosition = (overrides: Partial<PortfolioPosition>): PortfolioPosition => ({
  id: 1,
  broker: 'IBKR',
  symbol: 'AAPL',
  quantity: 1,
  avg_cost: 100,
  currency: 'USD',
  is_active: true,
  ...overrides,
})

describe('usePortfolioTickers', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('flags a currently held symbol as active', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => [makePosition({ symbol: 'AAPL', is_active: true })],
    } as Response)

    const { result } = renderHook(() => usePortfolioTickers())

    await waitFor(() => expect(result.current('AAPL')).toBe('active'))
    expect(result.current('aapl')).toBe('active')
  })

  it('flags a position closed within the last 30 days as recent', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => [
        makePosition({ symbol: 'TSLA', is_active: false, updated_at: daysAgo(10) }),
      ],
    } as Response)

    const { result } = renderHook(() => usePortfolioTickers())

    await waitFor(() => expect(result.current('TSLA')).toBe('recent'))
  })

  it('does not flag a position closed more than 30 days ago', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => [
        makePosition({ symbol: 'NVDA', is_active: false, updated_at: daysAgo(45) }),
      ],
    } as Response)

    const { result } = renderHook(() => usePortfolioTickers())

    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(result.current('NVDA')).toBeNull()
  })

  it('prefers active over a stale closed record for the same symbol', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => [
        makePosition({ id: 1, symbol: 'MSFT', is_active: false, updated_at: daysAgo(5) }),
        makePosition({ id: 2, symbol: 'MSFT', is_active: true }),
      ],
    } as Response)

    const { result } = renderHook(() => usePortfolioTickers())

    await waitFor(() => expect(result.current('MSFT')).toBe('active'))
  })

  it('returns null for a symbol never held', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => [] } as Response)

    const { result } = renderHook(() => usePortfolioTickers())

    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(result.current('GOOG')).toBeNull()
  })
})
