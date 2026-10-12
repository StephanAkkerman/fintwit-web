import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MarketPositioningWidget from './MarketPositioningWidget'
import type { MarketPositioning } from '../types'

vi.mock('../hooks/useMarketPositioning', () => ({
  useMarketPositioning: vi.fn(),
}))

import { useMarketPositioning } from '../hooks/useMarketPositioning'
const mockUseMarketPositioning = vi.mocked(useMarketPositioning)

const DATA: MarketPositioning = {
  futures: [
    {
      code: '13874A',
      name: 'E-mini S&P 500',
      report_date: '2026-10-06',
      open_interest: 1_932_227,
      lev_net: -415_087,
      lev_net_pct_oi: -21.48,
      lev_net_change: -42_598,
      lev_percentile: 10.8,
      asset_mgr_net: 906_615,
      asset_mgr_net_pct_oi: 46.92,
      crowding: 'crowded_short',
      weeks_ranked: 158,
      history: [
        { date: '2026-09-29', lev_net_pct_oi: -19.5 },
        { date: '2026-10-06', lev_net_pct_oi: -21.48 },
      ],
    },
  ],
  cta: {
    symbol: 'SPY',
    spot: 778.57,
    score: 0,
    exposure: 'flat',
    nearest_trigger: '1M',
    signals: [
      { lookback: '1M', days: 21, trigger: 780.1, distance_pct: -0.2, signal: 'short' },
      { lookback: '3M', days: 63, trigger: 749.17, distance_pct: 3.92, signal: 'long' },
    ],
  },
  concentration: {
    cap_weighted: 'SPY',
    equal_weighted: 'RSP',
    trend: 'narrowing',
    headline_window: '3M',
    windows: [{ window: '3M', cap_weighted_pct: 3.92, equal_weighted_pct: -0.56, spread_pp: -4.48 }],
    ratio_history: [
      { date: '2025-10-10', ratio: 100 },
      { date: '2026-10-10', ratio: 96.5 },
    ],
  },
  as_of: '2026-10-11T12:00:00Z',
}

function mockState(overrides: Partial<ReturnType<typeof useMarketPositioning>> = {}) {
  mockUseMarketPositioning.mockReturnValue({
    data: DATA,
    loading: false,
    error: false,
    ...overrides,
  })
}

describe('MarketPositioningWidget', () => {
  beforeEach(() => mockUseMarketPositioning.mockReset())

  it('shows hedge fund crowding, CTA exposure and breadth', () => {
    mockState()
    render(<MarketPositioningWidget />)

    expect(screen.getByText('E-mini S&P 500')).toBeInTheDocument()
    expect(screen.getByText('Crowded short')).toBeInTheDocument()
    expect(screen.getByText('-21.5% of OI')).toBeInTheDocument()
    expect(screen.getByText('Flat')).toBeInTheDocument()
    expect(screen.getByText('780.10')).toBeInTheDocument()
    expect(screen.getByText('Narrowing')).toBeInTheDocument()
    expect(screen.getByText('-4.5pp')).toBeInTheDocument()
  })

  it('keeps the other sections when one source is down', () => {
    mockState({ data: { ...DATA, futures: null, cta: null } })
    render(<MarketPositioningWidget />)

    expect(screen.getAllByText('Source unavailable right now.')).toHaveLength(2)
    expect(screen.getByText('Narrowing')).toBeInTheDocument()
  })

  it('shows an error when the endpoint fails', () => {
    mockState({ data: null, error: true })
    render(<MarketPositioningWidget />)

    expect(screen.getByText('Could not load market positioning data.')).toBeInTheDocument()
  })
})
