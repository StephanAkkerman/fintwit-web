import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CongressTradesWidget from './CongressTradesWidget'
import type { CongressTrade, CongressTrades } from '../types'

vi.mock('../hooks/useCongressTrades', () => ({
  useCongressTrades: vi.fn(),
}))

import { useCongressTrades } from '../hooks/useCongressTrades'
const mockUseCongressTrades = vi.mocked(useCongressTrades)

function trade(
  ticker: string,
  transaction: CongressTrade['transaction'],
  politician: string,
  party: string,
  excess: number | null,
  label = transaction === 'buy' ? 'Purchase' : 'Sale',
): CongressTrade {
  return {
    id: `${politician}-${ticker}`,
    ticker,
    asset: `${ticker} INC`,
    asset_type: 'ST',
    transaction,
    transaction_label: label,
    amount_range: '$1,001 - $15,000',
    amount_min: 1001,
    amount_max: 15000,
    politician,
    chamber: 'House',
    party,
    party_name: party === 'D' ? 'Democrat' : 'Republican',
    filed: '2026-10-15',
    traded: '2026-10-09',
    description: null,
    excess_return_pct: excess,
    photo_url: null,
    bioguide_id: null,
    website: null,
  }
}

const DATA: CongressTrades = {
  trades: [
    trade('NVDA', 'buy', 'Nancy Pelosi', 'D', 12.4),
    trade('HD', 'sell', 'Kevin Hern', 'R', -2.1, 'Sale (Partial)'),
    trade('HD', 'sell', 'Rick Larsen', 'D', null),
  ],
  summary: {
    trades: 3,
    buys: 1,
    sells: 2,
    most_bought: [{ ticker: 'NVDA', trades: 1, politicians: ['Nancy Pelosi'] }],
    most_sold: [{ ticker: 'HD', trades: 2, politicians: ['Kevin Hern', 'Rick Larsen'] }],
    politicians: [],
  },
  filter: { politician: null, stocks_only: true },
  as_of: '2026-10-15',
  source: 'quiver',
}

function rows() {
  return screen.getAllByRole('row').slice(1)
}

describe('CongressTradesWidget', () => {
  beforeEach(() => {
    mockUseCongressTrades.mockReset()
    mockUseCongressTrades.mockReturnValue({ data: DATA, loading: false, error: false })
  })

  it('lists trades with side, amount and excess return', () => {
    render(<CongressTradesWidget />)

    expect(screen.getByText('1 buys · 2 sells')).toBeInTheDocument()
    expect(rows()).toHaveLength(3)
    expect(screen.getByText('Sell (partial)')).toBeInTheDocument()
    expect(screen.getByText('+12.4%')).toHaveClass('text-emerald-600')
    expect(screen.getByText('-2.1%')).toHaveClass('text-rose-600')
    expect(screen.getAllByText('$1K–$15K')).toHaveLength(3)
    expect(screen.getByText('2 members')).toBeInTheDocument()
  })

  it('filters by member', () => {
    render(<CongressTradesWidget />)

    fireEvent.change(screen.getByLabelText('Filter by member'), { target: { value: 'Nancy Pelosi' } })
    expect(rows()).toHaveLength(1)
    expect(within(rows()[0]).getByText('NVDA')).toBeInTheDocument()
  })

  it('filters to a ticker from the most-sold list, and clears it', () => {
    render(<CongressTradesWidget />)

    fireEvent.click(screen.getByTitle('Kevin Hern, Rick Larsen'))
    expect(rows()).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Sells' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByLabelText('Clear HD filter'))
    fireEvent.click(screen.getByRole('button', { name: 'All' }))
    expect(rows()).toHaveLength(3)
  })

  it('shows empty and error states', () => {
    mockUseCongressTrades.mockReturnValue({ data: { ...DATA, trades: [] }, loading: false, error: false })
    const { unmount } = render(<CongressTradesWidget />)
    expect(screen.getByText('No congressional trade disclosures available right now.')).toBeInTheDocument()
    unmount()

    mockUseCongressTrades.mockReturnValue({ data: null, loading: false, error: true })
    render(<CongressTradesWidget />)
    expect(screen.getByText('Could not load congress trades.')).toBeInTheDocument()
  })
})
