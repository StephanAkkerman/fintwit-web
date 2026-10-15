import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WorldIndicesWidget from './WorldIndicesWidget'
import type { WorldIndex, WorldIndices } from '../types'

vi.mock('../hooks/useWorldIndices', () => ({
  useWorldIndices: vi.fn(),
}))

import { useWorldIndices } from '../hooks/useWorldIndices'
const mockUseWorldIndices = vi.mocked(useWorldIndices)

function index(overrides: Partial<WorldIndex>): WorldIndex {
  return {
    symbol: 'KOSPI',
    name: 'KOSPI',
    country: 'KR',
    region: 'asia',
    price: 5554.22,
    change_percent: -7.57,
    timezone: 'Asia/Seoul',
    read_through: 'Samsung, SK Hynix: memory (MU, SNDK, WDC)',
    tags: ['semis'],
    tv_symbol: 'KRX:KOSPI',
    website: 'https://www.tradingview.com/symbols/KRX-KOSPI/',
    is_open: false,
    session_date: '2026-10-15',
    next_open: null,
    ...overrides,
  }
}

const DATA: WorldIndices = {
  as_of: '2026-10-15T17:40:00Z',
  regions: [
    { key: 'asia', label: 'Asia-Pacific', avg_change_percent: -2.42, indices: [index({})] },
    {
      key: 'us_futures',
      label: 'US futures',
      avg_change_percent: 0.3,
      indices: [
        index({
          symbol: 'NQ',
          name: 'Nasdaq 100 futures',
          country: 'US',
          region: 'us_futures',
          change_percent: 0.6,
          read_through: 'Where the Nasdaq 100 is set to open',
          tags: [],
          is_open: true,
          session_date: null,
        }),
      ],
    },
  ],
  semis: { avg_change_percent: -4.07, tone: 'bearish', symbols: ['NI225', 'KOSPI'] },
  source: 'tradingview',
}

function mockState(overrides: Partial<ReturnType<typeof useWorldIndices>> = {}) {
  mockUseWorldIndices.mockReturnValue({ data: DATA, loading: false, error: false, ...overrides })
}

describe('WorldIndicesWidget', () => {
  beforeEach(() => mockUseWorldIndices.mockReset())

  it('shows each region with moves, session state and read-through', () => {
    mockState()
    render(<WorldIndicesWidget />)

    expect(screen.getByText('Asia-Pacific')).toBeInTheDocument()
    expect(screen.getByText('avg -2.42%')).toBeInTheDocument()
    expect(screen.getByText('-7.57%')).toBeInTheDocument()
    expect(screen.getByText('Closed · Oct 15')).toBeInTheDocument()
    expect(screen.getByText('Samsung, SK Hynix: memory (MU, SNDK, WDC)')).toBeInTheDocument()
    expect(screen.getByText('Open')).toBeInTheDocument()
    expect(screen.getByText('+0.60%')).toBeInTheDocument()
  })

  it('flags a chip sell-off as pressure on US semis', () => {
    mockState()
    render(<WorldIndicesWidget />)

    expect(
      screen.getByText('Chip-heavy indices -4.07%: pressure on US semis'),
    ).toBeInTheDocument()
  })

  it('shows an error when the endpoint fails', () => {
    mockState({ data: null, error: true })
    render(<WorldIndicesWidget />)

    expect(screen.getByText('Could not load world market data.')).toBeInTheDocument()
  })
})
