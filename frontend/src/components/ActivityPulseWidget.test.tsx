import { fireEvent, render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ActivityPulseWidget } from './ActivityPulseWidget'
import type { ActivitySummary } from '../types'

vi.mock('../hooks/useActivitySummary', () => ({
  useActivitySummary: vi.fn(),
}))

import { useActivitySummary } from '../hooks/useActivitySummary'
const mockUseActivitySummary = vi.mocked(useActivitySummary)

const sample = (overrides: Partial<ActivitySummary> = {}): ActivitySummary => ({
  window_hours: 24,
  tweets: { current: 312, previous: 264 },
  authors: { current: 48, previous: 44 },
  sentiment: { bull: 124, bear: 76, bull_pct: 62, prev_bull_pct: 55 },
  top_ticker: {
    ticker: 'NVDA', mentions: 41, unique_authors: 19, avg_sentiment: 0.4,
    sentiment_label: 'BULL', asset_kind: 'EQUITY', price_direction: 2.1,
  },
  top_mover: {
    ticker: 'SOL', mentions: 9, unique_authors: 6, avg_sentiment: 0.3,
    sentiment_label: 'BULL', asset_kind: 'CRYPTO', price_direction: -8.24,
  },
  ...overrides,
})

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ActivityPulseWidget', () => {
  it('shows a loading skeleton', () => {
    mockUseActivitySummary.mockReturnValue({ data: null, loading: true, error: false })
    render(<ActivityPulseWidget assetKind="all" />)
    expect(document.querySelector('.animate-pulse')).not.toBeNull()
  })

  it('shows an error message', () => {
    mockUseActivitySummary.mockReturnValue({ data: null, loading: false, error: true })
    render(<ActivityPulseWidget assetKind="all" />)
    expect(screen.getByText(/Failed to load activity summary/i)).toBeInTheDocument()
  })

  it('shows an empty state when there is no activity', () => {
    mockUseActivitySummary.mockReturnValue({
      data: sample({
        tweets: { current: 0, previous: 0 },
        authors: { current: 0, previous: 0 },
        sentiment: { bull: 0, bear: 0, bull_pct: null, prev_bull_pct: null },
        top_ticker: null,
        top_mover: null,
      }),
      loading: false,
      error: false,
    })
    render(<ActivityPulseWidget assetKind="all" />)
    expect(screen.getByText(/No tweets in this window yet/i)).toBeInTheDocument()
  })

  it('renders the tiles with deltas vs the previous window', () => {
    mockUseActivitySummary.mockReturnValue({ data: sample(), loading: false, error: false })
    render(<ActivityPulseWidget assetKind="all" windowHours={24} />)

    expect(screen.getByText('312')).toBeInTheDocument()
    expect(screen.getByText('▲ 18%')).toBeInTheDocument()   // (312-264)/264
    expect(screen.getByText('48')).toBeInTheDocument()
    expect(screen.getByText('▲ 4')).toBeInTheDocument()
    expect(screen.getByText('62% bull')).toBeInTheDocument()
    expect(screen.getByText('▲ 7pt')).toBeInTheDocument()
    expect(screen.getByText('NVDA')).toBeInTheDocument()
    expect(screen.getByText('41×')).toBeInTheDocument()
    expect(screen.getByText('SOL')).toBeInTheDocument()
    expect(screen.getByText('-8.24%')).toBeInTheDocument()
    expect(screen.getByText(/last 24h vs previous 24h/)).toBeInTheDocument()
  })

  it('labels a bearish majority as bear share', () => {
    mockUseActivitySummary.mockReturnValue({
      data: sample({ sentiment: { bull: 30, bear: 70, bull_pct: 30, prev_bull_pct: null } }),
      loading: false,
      error: false,
    })
    render(<ActivityPulseWidget assetKind="all" />)
    expect(screen.getByText('70% bear')).toBeInTheDocument()
  })

  it('opens a ticker when clicked', () => {
    const onTickerClick = vi.fn()
    mockUseActivitySummary.mockReturnValue({ data: sample(), loading: false, error: false })
    render(<ActivityPulseWidget assetKind="all" onTickerClick={onTickerClick} />)
    fireEvent.click(screen.getByRole('button', { name: 'NVDA' }))
    expect(onTickerClick).toHaveBeenCalledWith('NVDA')
  })
})
