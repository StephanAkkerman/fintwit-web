import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MarketBreadthWidget from './MarketBreadthWidget'
import type { BreadthUniverse, MarketBreadth } from '../types'

vi.mock('../hooks/useMarketBreadth', () => ({
  useMarketBreadth: vi.fn(),
  useMarketBreadthHistory: vi.fn(() => []),
}))

import { useMarketBreadth, useMarketBreadthHistory } from '../hooks/useMarketBreadth'
const mockUseMarketBreadth = vi.mocked(useMarketBreadth)
const mockUseHistory = vi.mocked(useMarketBreadthHistory)

function universe(overrides: Partial<BreadthUniverse>): BreadthUniverse {
  return {
    key: 'spx',
    label: 'S&P 500',
    benchmark: { symbol: 'SPY', price: 763.25, change_pct: -1.11 },
    members: 503,
    advancers: 249,
    decliners: 254,
    unchanged: 0,
    advancers_pct: 49.5,
    new_highs: 20,
    new_lows: 1,
    pct_above_sma20: 68.5,
    pct_above_sma50: 45,
    pct_above_sma200: 51.8,
    read: {
      trend: { key: 'mixed', label: 'Mixed' },
      day: 'mixed',
      note: 'About half the members moved with the index.',
    },
    ...overrides,
  }
}

const DATA: MarketBreadth = {
  universes: [
    universe({}),
    universe({
      key: 'rut',
      label: 'Russell 2000',
      benchmark: { symbol: 'IWM', price: 270.44, change_pct: -1.69 },
      members: 1925,
      advancers: 549,
      decliners: 1349,
      new_highs: 39,
      new_lows: 105,
      pct_above_sma200: 42.9,
      read: {
        trend: { key: 'mixed', label: 'Mixed' },
        day: 'broad_selloff',
        note: 'Most members are falling with the index. New lows outnumber new highs.',
      },
    }),
  ],
  sectors: [
    {
      sector: 'Energy Minerals',
      members: 13,
      advancers: 13,
      decliners: 0,
      pct_above_sma50: 100,
      pct_above_sma200: 84.6,
      new_highs: 5,
      new_lows: 0,
      avg_change: 2.64,
    },
  ],
  session_date: '2026-10-16',
  as_of: '2026-10-19T08:10:46Z',
  source: 'tradingview',
}

describe('MarketBreadthWidget', () => {
  beforeEach(() => {
    mockUseMarketBreadth.mockReturnValue({ data: DATA, loading: false, error: false })
    mockUseHistory.mockReturnValue([])
  })

  it('shows each index and the selected one in detail', () => {
    render(<MarketBreadthWidget />)

    expect(screen.getByText('Session 2026-10-16')).toBeInTheDocument()
    expect(screen.getAllByText('52%')).toHaveLength(2)
    expect(screen.getByText('S&P 500 participation')).toBeInTheDocument()
    expect(screen.getByText('About half the members moved with the index.')).toBeInTheDocument()
    expect(screen.getByText('Energy Minerals')).toBeInTheDocument()
    expect(screen.getByText(/fills in as each trading session/)).toBeInTheDocument()
  })

  it('switches the detail when another index is picked', () => {
    render(<MarketBreadthWidget />)

    fireEvent.click(screen.getByRole('button', { name: /Russell 2000/ }))

    expect(screen.getByText('Russell 2000 participation')).toBeInTheDocument()
    expect(screen.getByText('Broad sell-off')).toBeInTheDocument()
    expect(screen.getByText('105')).toBeInTheDocument()
    expect(mockUseHistory).toHaveBeenLastCalledWith('rut')
  })

  it('shows an error when the endpoint fails', () => {
    mockUseMarketBreadth.mockReturnValue({ data: null, loading: false, error: true })
    render(<MarketBreadthWidget />)
    expect(screen.getByText('Could not load market breadth.')).toBeInTheDocument()
  })
})
