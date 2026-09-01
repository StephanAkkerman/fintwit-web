import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PortfolioDiversification from './PortfolioDiversification'
import type { PortfolioInsights } from '../types'

vi.mock('../hooks/usePortfolioInsights', () => ({
  usePortfolioInsights: vi.fn(),
}))

import { usePortfolioInsights } from '../hooks/usePortfolioInsights'
const mockUseInsights = vi.mocked(usePortfolioInsights)

const INSIGHTS: PortfolioInsights = {
  source: 'ibkr',
  totals: {
    positions: 2,
    market_value: 2970,
    cost_basis: 2000,
    unrealized_pnl: 970,
    unrealized_pnl_percent: 48.5,
  },
  positions: [],
  highlights: [],
  sectors: [
    {
      sector: 'Technology',
      market_value: 1980,
      weight_percent: 66.7,
      symbols: ['AAPL'],
    },
    {
      sector: 'Crypto',
      market_value: 990,
      weight_percent: 33.3,
      symbols: ['BTC'],
    },
  ],
  diversification: {
    label: 'concentrated',
    tone: 'bearish',
    holding_hhi: 0.55,
    effective_holdings: 1.8,
    sector_hhi: 0.5,
    effective_sectors: 2,
    top_holding: { symbol: 'AAPL', weight_percent: 66.7 },
    top_sector: { sector: 'Technology', weight_percent: 66.7 },
  },
}

function mockState(overrides: Partial<ReturnType<typeof usePortfolioInsights>> = {}) {
  mockUseInsights.mockReturnValue({
    insights: INSIGHTS,
    loading: false,
    error: null,
    reload: vi.fn(),
    ...overrides,
  } as ReturnType<typeof usePortfolioInsights>)
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('PortfolioDiversification', () => {
  it('shows a skeleton while loading', () => {
    mockState({ insights: null, loading: true })
    render(<PortfolioDiversification />)
    expect(document.querySelector('.animate-pulse')).not.toBeNull()
  })

  it('renders the sector breakdown with weights', () => {
    mockState()
    render(<PortfolioDiversification />)

    expect(screen.getByText('Technology')).toBeInTheDocument()
    expect(screen.getByText('Crypto')).toBeInTheDocument()
    // Unique to the Crypto row's value column, so this also proves the row rendered.
    expect(screen.getByText('$990 · 33.3%')).toBeInTheDocument()
  })

  it('shows the balance label and top holding/sector', () => {
    mockState()
    render(<PortfolioDiversification />)

    expect(screen.getByText('Concentrated')).toBeInTheDocument()
    expect(screen.getByText('AAPL · 66.7%')).toBeInTheDocument()
    expect(screen.getByText('Technology · 66.7%')).toBeInTheDocument()
  })

  it('shows an empty state without holdings', () => {
    mockState({
      insights: {
        ...INSIGHTS,
        sectors: [],
        diversification: {
          label: 'unrated',
          tone: 'neutral',
          holding_hhi: null,
          effective_holdings: null,
          sector_hhi: null,
          effective_sectors: null,
          top_holding: null,
          top_sector: null,
        },
      },
    })
    render(<PortfolioDiversification />)

    expect(screen.getByText(/no holdings yet/i)).toBeInTheDocument()
  })

  it('surfaces load errors', () => {
    mockState({ insights: null, error: 'Failed to load portfolio insights (503)' })
    render(<PortfolioDiversification />)

    expect(screen.getByText(/failed to load portfolio insights/i)).toBeInTheDocument()
  })
})
