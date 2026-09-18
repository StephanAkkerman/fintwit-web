import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { SectorMentionsWidget } from './SectorMentionsWidget'
import type { SectorMentionItem } from '../types'

vi.mock('../hooks/useSectorMentions', () => ({
  useSectorMentions: vi.fn(),
}))

import { useSectorMentions } from '../hooks/useSectorMentions'
const mockUseSectorMentions = vi.mocked(useSectorMentions)

const techSector: SectorMentionItem = {
  sector: 'Technology',
  mentions: 12,
  mention_score: 9,
  unique_authors: 5,
  unique_tickers: 2,
  avg_sentiment_24h: 0.4,
  sentiment_label_24h: 'BULL',
  top_tickers: [
    { ticker: 'NVDA', mentions: 7 },
    { ticker: 'MU', mentions: 5 },
  ],
  industries: [
    {
      industry: 'Semiconductors',
      mentions: 12,
      unique_tickers: 2,
      top_tickers: [
        { ticker: 'NVDA', mentions: 7 },
        { ticker: 'MU', mentions: 5 },
      ],
      trend: 'hot',
    },
  ],
  trend: 'hot',
  prev_mentions: 4,
  pct_change: 2,
}

const singleIndustrySector: SectorMentionItem = {
  sector: 'Energy',
  mentions: 3,
  mention_score: 3,
  unique_authors: 3,
  unique_tickers: 1,
  avg_sentiment_24h: 0,
  sentiment_label_24h: 'NEUTRAL',
  top_tickers: [{ ticker: 'XOM', mentions: 3 }],
  industries: [
    { industry: 'Other', mentions: 3, unique_tickers: 1, top_tickers: [{ ticker: 'XOM', mentions: 3 }] },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SectorMentionsWidget', () => {
  it('shows loading skeleton when loading is true', () => {
    mockUseSectorMentions.mockReturnValue({ data: [], loading: true, error: false })
    render(<SectorMentionsWidget />)
    expect(document.querySelector('.animate-pulse')).not.toBeNull()
  })

  it('shows error message when error is true', () => {
    mockUseSectorMentions.mockReturnValue({ data: [], loading: false, error: true })
    render(<SectorMentionsWidget />)
    expect(screen.getByText(/Failed to load sector mentions/i)).toBeTruthy()
  })

  it('shows empty state when data is empty and loading is false', () => {
    mockUseSectorMentions.mockReturnValue({ data: [], loading: false, error: false })
    render(<SectorMentionsWidget />)
    expect(screen.getByText(/No sector data yet/i)).toBeTruthy()
  })

  it('renders sector rows with mention counts and top tickers', () => {
    mockUseSectorMentions.mockReturnValue({ data: [techSector], loading: false, error: false })
    render(<SectorMentionsWidget />)

    expect(screen.getByText('Technology')).toBeTruthy()
    expect(screen.getByText(/12 mentions/)).toBeTruthy()
    expect(screen.getByText('$NVDA')).toBeTruthy()
    expect(screen.getByText('$MU')).toBeTruthy()
  })

  it('does not offer expansion when the sector has a single "Other" industry', () => {
    mockUseSectorMentions.mockReturnValue({ data: [singleIndustrySector], loading: false, error: false })
    render(<SectorMentionsWidget />)

    const toggle = screen.getByRole('button', { name: /Energy/ })
    expect(toggle).not.toHaveAttribute('aria-expanded')
  })

  it('expands a sector to reveal its industry breakdown', () => {
    mockUseSectorMentions.mockReturnValue({ data: [techSector], loading: false, error: false })
    render(<SectorMentionsWidget />)

    expect(screen.queryByText('Semiconductors')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Technology/ }))
    expect(screen.getByText('Semiconductors')).toBeTruthy()
  })

  it('calls onTickerClick when a ticker chip is clicked', () => {
    const onTickerClick = vi.fn()
    mockUseSectorMentions.mockReturnValue({ data: [techSector], loading: false, error: false })
    render(<SectorMentionsWidget onTickerClick={onTickerClick} />)

    fireEvent.click(screen.getByText('$NVDA'))
    expect(onTickerClick).toHaveBeenCalledWith('NVDA')
  })

  it('shows a trend badge with an emoji for a hot sector', () => {
    mockUseSectorMentions.mockReturnValue({ data: [techSector], loading: false, error: false })
    render(<SectorMentionsWidget />)

    expect(screen.getAllByText('Hot').length).toBeGreaterThan(0)
    expect(screen.getAllByText('🔥').length).toBeGreaterThan(0)
  })
})
