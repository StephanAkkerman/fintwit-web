import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import FundHoldingsWidget from './FundHoldingsWidget'
import type { Fund, FundHoldings, FundPosition } from '../types'

vi.mock('../hooks/useFundHoldings', () => ({
  useFundHoldings: vi.fn(),
}))

import { useFundHoldings } from '../hooks/useFundHoldings'
const mockUseFundHoldings = vi.mocked(useFundHoldings)

function position(overrides: Partial<FundPosition>): FundPosition {
  return {
    cusip: '037833100',
    issuer: 'APPLE INC',
    ticker: 'AAPL',
    instrument: null,
    value: 65_950_000_000,
    shares: 227_917_808,
    prev_shares: 227_917_808,
    weight_pct: 22.04,
    action: 'unchanged',
    shares_change_pct: 0,
    value_change: 0,
    ...overrides,
  }
}

function fund(overrides: Partial<Fund>): Fund {
  return {
    cik: 1067983,
    name: 'Berkshire Hathaway',
    manager: 'Warren Buffett',
    report_date: '2026-06-30',
    filed: '2026-08-14',
    prev_report_date: '2026-03-31',
    filing_url: 'https://www.sec.gov/filing',
    positions: 29,
    total_value: 299_253_556_246,
    top_holdings: [position({})],
    buys: [
      position({ cusip: 'G', ticker: 'GOOGL', issuer: 'ALPHABET', action: 'added', shares_change_pct: 45.2, value_change: 8_770_000_000 }),
    ],
    sells: [position({ cusip: 'N', ticker: 'NUE', issuer: 'NUCOR', action: 'reduced', shares_change_pct: -52.4, value_change: -460_000_000 })],
    new_positions: 1,
    sold_out: 1,
    stale: false,
    ...overrides,
  }
}

const DATA: FundHoldings = {
  funds: [
    fund({}),
    fund({
      cik: 1536411,
      name: 'Duquesne Family Office',
      manager: 'Stanley Druckenmiller',
      total_value: 5_210_856_000,
      top_holdings: [position({ cusip: 'NT', ticker: 'NTRA', issuer: 'Natera Inc', weight_pct: 16.6 })],
      buys: [position({ cusip: 'IN', ticker: 'INSM', issuer: 'Insmed', action: 'new', value_change: 152_000_000 })],
      sells: [],
    }),
  ],
  most_bought: [{ cusip: 'G', issuer: 'ALPHABET', ticker: 'GOOGL', funds: ['A', 'B', 'C'], new_or_exited: 1, value_change: 1 }],
  most_sold: [{ cusip: 'T', issuer: 'TSMC', ticker: 'TSM', funds: ['A', 'B'], new_or_exited: 0, value_change: -1 }],
  most_held: [{ cusip: 'A', issuer: 'AMAZON', ticker: 'AMZN', funds: ['A', 'B', 'C', 'D'], value: 1 }],
  report_date: '2026-06-30',
  missing: ['Pershing Square'],
  as_of: '2026-10-19T08:00:00Z',
  source: 'sec-13f',
}

describe('FundHoldingsWidget', () => {
  beforeEach(() => {
    mockUseFundHoldings.mockReturnValue({ data: DATA, loading: false, error: false })
  })

  it('shows cross-fund moves and the biggest fund first', () => {
    render(<FundHoldingsWidget />)

    expect(screen.getByText('$GOOGL')).toBeInTheDocument()
    expect(screen.getByText('$TSM')).toBeInTheDocument()
    expect(screen.getByText('$AMZN')).toBeInTheDocument()
    expect(screen.getByText('Warren Buffett', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('+45%')).toBeInTheDocument()
    expect(screen.getByText('-52%')).toBeInTheDocument()
    expect(screen.getByText(/Could not load: Pershing Square/)).toBeInTheDocument()
  })

  it('switches to another fund', () => {
    render(<FundHoldingsWidget />)

    fireEvent.click(screen.getByRole('button', { name: 'Duquesne Family Office' }))

    expect(screen.getByText('NTRA')).toBeInTheDocument()
    expect(screen.getByText('INSM')).toBeInTheDocument()
    expect(screen.getByText('No changes.')).toBeInTheDocument()
  })

  it('shows an error when the endpoint fails', () => {
    mockUseFundHoldings.mockReturnValue({ data: null, loading: false, error: true })
    render(<FundHoldingsWidget />)
    expect(screen.getByText('Could not load fund holdings.')).toBeInTheDocument()
  })
})
