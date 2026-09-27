import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import GammaExposureWidget from './GammaExposureWidget'
import type { GammaExposureHistoryPoint, GammaExposureSnapshot } from '../types'

vi.mock('../hooks/useGammaExposure', () => ({
  useGammaExposure: vi.fn(),
}))

import { useGammaExposure } from '../hooks/useGammaExposure'
const mockUseGammaExposure = vi.mocked(useGammaExposure)

const SNAPSHOT: GammaExposureSnapshot = {
  symbol: 'SPY',
  spot_price: 500.25,
  net_gex: -1_500_000_000,
  call_gex: 2_000_000_000,
  put_gex: -3_500_000_000,
  flip_point: 505.5,
  regime: 'negative',
  expirations_used: ['2026-10-17'],
  by_strike: [],
  as_of: '2026-09-27T12:00:00Z',
  source: 'yfinance-bs-estimate',
}

const HISTORY: GammaExposureHistoryPoint[] = [
  {
    id: 1,
    symbol: 'SPY',
    captured_at: '2026-09-27T10:00:00Z',
    spot_price: 498.0,
    net_gex: 1_000_000_000,
    call_gex: 2_000_000_000,
    put_gex: -1_000_000_000,
    flip_point: 500.0,
    regime: 'positive',
  },
  {
    id: 2,
    symbol: 'SPY',
    captured_at: '2026-09-27T12:00:00Z',
    spot_price: 500.25,
    net_gex: -1_500_000_000,
    call_gex: 2_000_000_000,
    put_gex: -3_500_000_000,
    flip_point: 505.5,
    regime: 'negative',
  },
]

function mockState(overrides: Partial<ReturnType<typeof useGammaExposure>> = {}) {
  mockUseGammaExposure.mockReturnValue({
    snapshot: SNAPSHOT,
    history: HISTORY,
    loading: false,
    error: false,
    ...overrides,
  } as ReturnType<typeof useGammaExposure>)
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('GammaExposureWidget', () => {
  it('shows a skeleton while loading', () => {
    mockState({ loading: true })
    render(<GammaExposureWidget />)
    expect(document.querySelector('.animate-pulse')).not.toBeNull()
  })

  it('renders the current regime badge and stats', () => {
    mockState()
    render(<GammaExposureWidget />)

    expect(screen.getByText(/spy gamma exposure/i)).toBeInTheDocument()
    expect(screen.getByText('Negative Gamma')).toBeInTheDocument()
    expect(screen.getByText('500.25')).toBeInTheDocument()
    expect(screen.getByText('-$1.50B')).toBeInTheDocument()
    expect(screen.getByText('505.50')).toBeInTheDocument()
  })

  it('shows a positive gamma badge when the regime is positive', () => {
    mockState({ snapshot: { ...SNAPSHOT, regime: 'positive', net_gex: 1_200_000_000 } })
    render(<GammaExposureWidget />)

    expect(screen.getByText('Positive Gamma')).toBeInTheDocument()
    expect(screen.getByText('$1.20B')).toBeInTheDocument()
  })

  it('prompts that history is still building when fewer than 2 points exist', () => {
    mockState({ history: [] })
    render(<GammaExposureWidget />)

    expect(screen.getByText(/regime history builds up/i)).toBeInTheDocument()
  })

  it('surfaces load errors', () => {
    mockState({ error: true })
    render(<GammaExposureWidget />)

    expect(screen.getByText(/could not load gamma exposure data/i)).toBeInTheDocument()
  })
})
