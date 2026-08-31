import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PortfolioValueChart from './PortfolioValueChart'
import type { PortfolioHistory } from '../types'

vi.mock('../hooks/usePortfolioHistory', () => ({
  usePortfolioHistory: vi.fn(),
  PORTFOLIO_RANGES: ['1W', '1M', '3M', '6M', 'YTD', '1Y', '5Y', 'MAX'],
}))

import { usePortfolioHistory } from '../hooks/usePortfolioHistory'
const mockUseHistory = vi.mocked(usePortfolioHistory)

const setRange = vi.fn()

const HISTORY: PortfolioHistory = {
  source: 'manual',
  range: '3M',
  available_ranges: ['1M', '3M', '1Y'],
  holdings: ['AAPL', 'MSFT'],
  points: [
    {
      t: '2026-01-02',
      value: 1000,
      cost_basis: 900,
      pnl: 100,
      pnl_percent: 11.11,
      source: 'reconstructed',
    },
    {
      t: '2026-01-03',
      value: 1250,
      cost_basis: 900,
      pnl: 350,
      pnl_percent: 38.89,
      source: 'snapshot',
    },
  ],
  cost_basis: 900,
  start_value: 1000,
  end_value: 1250,
  change: 250,
  change_percent: 25,
  missing_symbols: [],
}

function mockState(overrides: Partial<ReturnType<typeof usePortfolioHistory>> = {}) {
  mockUseHistory.mockReturnValue({
    history: HISTORY,
    range: '3M',
    setRange,
    ranges: ['1W', '1M', '3M', '6M', 'YTD', '1Y', '5Y', 'MAX'],
    loading: false,
    refreshing: false,
    error: null,
    reload: vi.fn(),
    ...overrides,
  } as ReturnType<typeof usePortfolioHistory>)
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('PortfolioValueChart', () => {
  it('shows a skeleton while loading', () => {
    mockState({ history: null, loading: true })
    render(<PortfolioValueChart />)
    expect(document.querySelector('.animate-pulse')).not.toBeNull()
  })

  it('renders the headline value and change for the range', () => {
    mockState()
    render(<PortfolioValueChart />)

    expect(screen.getByText(/portfolio value/i)).toBeInTheDocument()
    expect(screen.getByText('$1,250')).toBeInTheDocument()
    expect(screen.getByText(/\+25\.00%/)).toBeInTheDocument()
    expect(screen.getByText(/over 3M/i)).toBeInTheDocument()
  })

  it('offers the ranges the API reports and switches on click', () => {
    mockState()
    render(<PortfolioValueChart />)

    const oneYear = screen.getByRole('button', { name: '1Y' })
    expect(screen.queryByRole('button', { name: 'MAX' })).toBeNull()
    expect(screen.getByRole('button', { name: '3M' })).toHaveAttribute(
      'aria-pressed',
      'true'
    )

    fireEvent.click(oneYear)
    expect(setRange).toHaveBeenCalledWith('1Y')
  })

  it('exposes every point through a table view so values are not hover-only', () => {
    mockState()
    render(<PortfolioValueChart />)

    fireEvent.click(screen.getByRole('button', { name: /show table view/i }))

    // Also shown in the "Start of 3M" stat, so match on all occurrences.
    expect(screen.getAllByText('$1,000.00').length).toBeGreaterThan(0)
    expect(screen.getByText('recorded snapshot')).toBeInTheDocument()
    expect(screen.getByText('reconstructed from prices')).toBeInTheDocument()
  })

  it('prompts to add holdings when there is nothing to chart', () => {
    mockState({
      history: { ...HISTORY, points: [], holdings: [], end_value: null, change: null },
    })
    render(<PortfolioValueChart />)

    expect(screen.getByText(/no holdings to chart yet/i)).toBeInTheDocument()
  })

  it('warns about holdings that have no price history', () => {
    mockState({ history: { ...HISTORY, missing_symbols: ['GHOST'] } })
    render(<PortfolioValueChart />)

    expect(screen.getByText(/no price history for GHOST/i)).toBeInTheDocument()
  })

  it('surfaces load errors', () => {
    mockState({ history: null, error: 'Failed to load portfolio history (500)' })
    render(<PortfolioValueChart />)

    expect(screen.getByText(/failed to load portfolio history/i)).toBeInTheDocument()
  })
})
