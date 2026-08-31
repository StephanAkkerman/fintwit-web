import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PortfolioAssetInsights from './PortfolioAssetInsights'
import type { PortfolioInsightPosition, PortfolioInsights } from '../types'

vi.mock('../hooks/usePortfolioInsights', () => ({
  usePortfolioInsights: vi.fn(),
}))

import { usePortfolioInsights } from '../hooks/usePortfolioInsights'
const mockUseInsights = vi.mocked(usePortfolioInsights)

const AAPL: PortfolioInsightPosition = {
  symbol: 'AAPL',
  quantity: 10,
  avg_cost: 100,
  cost_basis: 1000,
  currency: 'USD',
  market_price: 198,
  market_value: 1980,
  unrealized_pnl: 980,
  unrealized_pnl_percent: 98,
  change_percent: 1.2,
  weight_percent: 66.7,
  stats: {
    symbol: 'AAPL',
    price: 198,
    last_close: 197,
    history_start: '1980-12-12',
    all_time_high: { value: 200, date: '2026-08-01' },
    all_time_low: { value: 10, date: '1982-07-08' },
    week_52_high: { value: 200, date: '2026-08-01' },
    week_52_low: { value: 120, date: '2025-10-10' },
    from_ath_percent: -1,
    from_atl_percent: 1880,
    from_52w_high_percent: -1,
    from_52w_low_percent: 65,
    range_position_52w: 97.5,
    days_since_ath: 30,
    days_since_atl: 16000,
    flags: [{ code: 'near_ath', label: '1.0% below ATH', tone: 'bullish' }],
  },
}

const NOHIST: PortfolioInsightPosition = {
  ...AAPL,
  symbol: 'GHOST',
  weight_percent: 33.3,
  market_value: 990,
  unrealized_pnl: -10,
  unrealized_pnl_percent: -1,
  stats: null,
}

const INSIGHTS: PortfolioInsights = {
  source: 'ibkr',
  totals: {
    positions: 2,
    market_value: 2970,
    cost_basis: 2000,
    unrealized_pnl: 970,
    unrealized_pnl_percent: 48.5,
  },
  positions: [AAPL, NOHIST],
  highlights: [
    {
      symbol: 'AAPL',
      code: 'near_ath',
      label: '1.0% below ATH',
      tone: 'bullish',
      weight_percent: 66.7,
    },
  ],
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

describe('PortfolioAssetInsights', () => {
  it('shows a skeleton while loading', () => {
    mockState({ insights: null, loading: true })
    render(<PortfolioAssetInsights />)
    expect(document.querySelector('.animate-pulse')).not.toBeNull()
  })

  it('renders per-asset ATH and ATL distance', () => {
    mockState()
    render(<PortfolioAssetInsights />)

    // 'AAPL' also appears in the highlight strip, so scope to its table row.
    const row = screen.getAllByRole('row').find((r) => within(r).queryByText('10 @ $100.00'))
    expect(row).toBeDefined()

    const cells = within(row!)
    expect(cells.getByText('-1.0%')).toBeInTheDocument()
    expect(cells.getByText('+1880.0%')).toBeInTheDocument()
    expect(cells.getByText(/\$200\.00 · 2026-08-01/)).toBeInTheDocument()
  })

  it('summarises flagged assets as highlight badges', () => {
    mockState()
    render(<PortfolioAssetInsights />)

    // Once in the highlight strip, once in the row's signal column.
    expect(screen.getAllByText('1.0% below ATH')).toHaveLength(2)
  })

  it('labels the holdings source', () => {
    mockState()
    render(<PortfolioAssetInsights />)
    expect(screen.getByText('IBKR positions')).toBeInTheDocument()

    mockState({ insights: { ...INSIGHTS, source: 'manual' } })
    render(<PortfolioAssetInsights />)
    expect(screen.getByText('Tracked positions')).toBeInTheDocument()
  })

  it('degrades gracefully for assets without history', () => {
    mockState({ insights: { ...INSIGHTS, positions: [NOHIST], highlights: [] } })
    render(<PortfolioAssetInsights />)

    expect(screen.getByText('GHOST')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('shows an empty state without holdings', () => {
    mockState({ insights: { ...INSIGHTS, positions: [], highlights: [] } })
    render(<PortfolioAssetInsights />)

    expect(screen.getByText(/no holdings yet/i)).toBeInTheDocument()
  })

  it('surfaces load errors', () => {
    mockState({ insights: null, error: 'Failed to load portfolio insights (503)' })
    render(<PortfolioAssetInsights />)

    expect(screen.getByText(/failed to load portfolio insights/i)).toBeInTheDocument()
  })
})
