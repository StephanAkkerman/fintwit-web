import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import InsiderTradesWidget from './InsiderTradesWidget'
import type { InsiderTrade, InsiderTrades } from '../types'

vi.mock('../hooks/useInsiderTrades', () => ({
  useInsiderTrades: vi.fn(),
}))

import { useInsiderTrades } from '../hooks/useInsiderTrades'
const mockUseInsiderTrades = vi.mocked(useInsiderTrades)

function trade(overrides: Partial<InsiderTrade>): InsiderTrade {
  return {
    filed_at: '2026-10-13 15:33:35',
    traded: '2026-10-08',
    ticker: 'HEI',
    company: 'Heico Corp',
    insider: 'Mendelson Victor H',
    insider_cik: '1',
    title: 'Co-COB, Co-CEO',
    is_officer: true,
    is_ten_percent_owner: false,
    side: 'buy',
    trade_label: 'P - Purchase',
    with_option_exercise: false,
    price: 220.3,
    shares: 795,
    owned_after: 10_000,
    owned_change_pct: 8,
    new_position: false,
    value: 175_142,
    remarks: [],
    filing_url: 'https://www.sec.gov/form4.xml',
    ...overrides,
  }
}

const group = (ticker: string, insiders: string[], value: number) => ({
  ticker,
  company: `${ticker} Inc`,
  insiders,
  officers: [],
  trades: insiders.length,
  value,
  last_traded: '2026-10-08',
  last_price: 10,
})

const DATA: InsiderTrades = {
  trades: [
    trade({}),
    trade({ insider: 'Fine Carol F.', title: 'Dir', is_officer: false }),
    trade({ ticker: 'FUL', company: 'Fuller H B Co', insider: 'Bailly R Jeffrey', title: 'Dir', is_officer: false, new_position: true }),
    trade({
      ticker: 'NVDA',
      company: 'Nvidia Corp',
      insider: 'Teter Timothy S.',
      title: 'EVP, GC',
      is_officer: false,
      side: 'sell',
      trade_label: 'S - Sale+OE',
      with_option_exercise: true,
      value: -6_786_533,
    }),
  ],
  summary: {
    buys: 3,
    sells: 1,
    buy_value: 850_000,
    sell_value: 6_786_533,
    buy_share_pct: 11.1,
    cluster_buys: [group('HEI', ['Fine Carol F.', 'Mendelson Victor H'], 350_284)],
    top_buys: [group('FUL', ['Bailly R Jeffrey'], 500_000)],
    top_sells: [group('AVGO', ['Tan Hock E'], 250_000_000)],
  },
  filter: { days: 30, min_value: 25_000, ticker: null, side: null },
  as_of: '2026-10-16 21:57:56',
  source: 'openinsider',
}

describe('InsiderTradesWidget', () => {
  beforeEach(() => {
    mockUseInsiderTrades.mockReturnValue({ data: DATA, loading: false, error: false })
  })

  it('shows the buy/sell balance, cluster buys and buys by default', () => {
    render(<InsiderTradesWidget />)

    expect(screen.getByText('3 buys · 1 sales')).toBeInTheDocument()
    expect(screen.getByText('Bought $850K')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /\$HEI/ })).toHaveTextContent('2 insiders')
    const table = screen.getByRole('table')
    expect(within(table).getAllByText('Buy')).toHaveLength(3)
    expect(within(table).queryByText('NVDA')).not.toBeInTheDocument()
    expect(within(table).getByText('New')).toBeInTheDocument()
  })

  it('filters by a picked ticker and by officers', () => {
    render(<InsiderTradesWidget />)

    fireEvent.click(screen.getByRole('button', { name: /\$HEI/ }))
    const table = screen.getByRole('table')
    expect(within(table).queryByText('FUL')).not.toBeInTheDocument()
    expect(within(table).getAllByText('HEI')).toHaveLength(2)

    fireEvent.click(screen.getByRole('checkbox'))
    expect(within(screen.getByRole('table')).getAllByText('HEI')).toHaveLength(1)
  })

  it('labels sales tied to an option exercise', () => {
    render(<InsiderTradesWidget />)
    fireEvent.click(screen.getByRole('button', { name: 'Sales' }))
    expect(screen.getByText('Sale + exercise')).toBeInTheDocument()
  })

  it('shows an error when the endpoint fails', () => {
    mockUseInsiderTrades.mockReturnValue({ data: null, loading: false, error: true })
    render(<InsiderTradesWidget />)
    expect(screen.getByText('Could not load insider trades.')).toBeInTheDocument()
  })
})
