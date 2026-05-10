import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MentionHeatmap } from './MentionHeatmap'
import type { MentionHeatCell } from '../types'

vi.mock('../hooks/useMentionHeat', () => ({
  useMentionHeat: vi.fn(),
}))

import { useMentionHeat } from '../hooks/useMentionHeat'
const mockUseMentionHeat = vi.mocked(useMentionHeat)

const sampleCells: MentionHeatCell[] = [
  {
    ticker: 'AAPL',
    mentions: 120,
    avg_sentiment_24h: 0.4,
    sentiment_label_24h: 'BULL',
    asset_kind: 'EQUITY',
    price_direction: 1,
  },
  {
    ticker: 'BTC',
    mentions: 80,
    avg_sentiment_24h: -0.2,
    sentiment_label_24h: 'BEAR',
    asset_kind: 'CRYPTO',
    price_direction: -1,
  },
]

beforeEach(() => {
  vi.clearAllMocks()
})

describe('MentionHeatmap', () => {
  it('shows loading skeleton when loading is true', () => {
    mockUseMentionHeat.mockReturnValue({ data: [], loading: true, error: false })
    render(<MentionHeatmap assetKind="all" />)
    const skeleton = document.querySelector('.animate-pulse')
    expect(skeleton).not.toBeNull()
  })

  it('shows empty state when data is empty and loading is false', () => {
    mockUseMentionHeat.mockReturnValue({ data: [], loading: false, error: false })
    render(<MentionHeatmap assetKind="all" />)
    expect(screen.getByText(/No tickers in the last/i)).toBeTruthy()
  })

  it('renders without crashing when data has cells', () => {
    mockUseMentionHeat.mockReturnValue({ data: sampleCells, loading: false, error: false })
    render(<MentionHeatmap assetKind="EQUITY" />)
    const container = document.querySelector('[data-testid="mention-heatmap-container"]')
    expect(container).not.toBeNull()
  })

  it('shows mention count for each ticker', () => {
    mockUseMentionHeat.mockReturnValue({ data: sampleCells, loading: false, error: false })
    render(<MentionHeatmap assetKind="EQUITY" />)
    expect(screen.getByText('120')).toBeTruthy()
    expect(screen.getByText('80')).toBeTruthy()
  })
})
