import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PortfolioPanel from '../components/PortfolioPanel'
import type { PortfolioPosition, PortfolioSummary } from '../types'

const mockUsePortfolio = vi.fn()

vi.mock('../hooks/usePortfolio', () => ({
  usePortfolio: () => mockUsePortfolio(),
}))

const baseSummary: PortfolioSummary = {
  totals: {
    positions: 1,
    market_value: 1200,
    cost_basis: 1000,
    unrealized_pnl: 200,
    unrealized_pnl_percent: 20,
  },
  positions: [
    {
      id: 1,
      symbol: 'AAPL',
      quantity: 10,
      avg_cost: 100,
      market_price: 120,
      market_value: 1200,
      cost_basis: 1000,
      unrealized_pnl: 200,
      unrealized_pnl_percent: 20,
      is_active: true,
    },
  ],
}

const basePositions: PortfolioPosition[] = [
  {
    id: 1,
    broker: 'IBKR',
    symbol: 'AAPL',
    quantity: 10,
    avg_cost: 100,
    currency: 'USD',
    notes: null,
    is_active: true,
    created_at: '2026-04-04T00:00:00Z',
    updated_at: '2026-04-04T00:00:00Z',
  },
]

describe('PortfolioPanel', () => {
  beforeEach(() => {
    mockUsePortfolio.mockReset()
    mockUsePortfolio.mockReturnValue({
      positions: basePositions,
      summary: baseSummary,
      loading: false,
      error: null,
      addPosition: vi.fn().mockResolvedValue(undefined),
      toggleActive: vi.fn().mockResolvedValue(undefined),
      removePosition: vi.fn().mockResolvedValue(undefined),
    })
  })

  it('renders the IBKR portfolio section and existing position', () => {
    render(<PortfolioPanel />)

    expect(screen.getByText(/ibkr portfolio/i)).toBeInTheDocument()
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText(/market value/i)).toBeInTheDocument()
  })

  it('submits a normalized symbol and numeric inputs', async () => {
    const addPosition = vi.fn().mockResolvedValue(undefined)
    mockUsePortfolio.mockReturnValue({
      positions: [],
      summary: null,
      loading: false,
      error: null,
      addPosition,
      toggleActive: vi.fn().mockResolvedValue(undefined),
      removePosition: vi.fn().mockResolvedValue(undefined),
    })

    render(<PortfolioPanel />)

    fireEvent.change(screen.getByLabelText('Portfolio symbol'), { target: { value: ' msft ' } })
    fireEvent.change(screen.getByLabelText('Portfolio quantity'), { target: { value: '5' } })
    fireEvent.change(screen.getByLabelText('Portfolio average cost'), { target: { value: '412.5' } })
    fireEvent.change(screen.getByLabelText('Portfolio notes'), { target: { value: 'Core position' } })

    fireEvent.click(screen.getByRole('button', { name: 'Add' }))

    await waitFor(() => {
      expect(addPosition).toHaveBeenCalledWith({
        symbol: 'MSFT',
        quantity: 5,
        avg_cost: 412.5,
        notes: 'Core position',
      })
    })
  })
})
