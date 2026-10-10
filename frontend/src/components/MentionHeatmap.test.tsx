import { fireEvent, render, screen } from '@testing-library/react'
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
    const tiles = screen.getAllByTestId('mention-heat-tile').map(t => t.textContent)
    expect(tiles[0]).toMatch(/AAPL.*120$/)
    expect(tiles[1]).toMatch(/BTC.*80$/)
  })

  it('orders tiles by fairness-adjusted score, not raw mentions', () => {
    const base = { avg_sentiment_24h: 0, sentiment_label_24h: 'NEUTRAL', price_direction: null } as const
    mockUseMentionHeat.mockReturnValue({
      data: [
        { ...base, ticker: 'EUR', mentions: 70, mention_score: 3, asset_kind: 'FOREX' },
        { ...base, ticker: 'NVDA', mentions: 30, mention_score: 25, asset_kind: 'EQUITY' },
      ],
      loading: false,
      error: false,
    })
    render(<MentionHeatmap assetKind="all" />)
    const tickers = screen.getAllByTestId('mention-heat-tile').map(b => b.textContent)
    expect(tickers[0]).toContain('NVDA')
  })

  it('groups tickers by sector, falling back to asset class', () => {
    const base = { sentiment_label_24h: 'NEUTRAL', price_direction: null, asset_kind: 'EQUITY' } as const
    mockUseMentionHeat.mockReturnValue({
      data: [
        { ...base, ticker: 'NVDA', mentions: 40, avg_sentiment_24h: 0.5, sector: 'Technology', industry: 'Semiconductors' },
        { ...base, ticker: 'AMD', mentions: 20, avg_sentiment_24h: 0.3, sector: 'Technology', industry: 'Semiconductors' },
        { ...base, ticker: 'XOM', mentions: 15, avg_sentiment_24h: -0.4, sector: 'Energy', industry: 'Oil & Gas' },
        { ...base, ticker: 'BTC', mentions: 30, avg_sentiment_24h: 0, asset_kind: 'CRYPTO' },
      ],
      loading: false,
      error: false,
    })
    render(<MentionHeatmap assetKind="all" />)
    expect(screen.getAllByTestId('mention-heat-group')).toHaveLength(3)
    expect(screen.getByRole('button', { name: 'Show Technology in detail' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Show Crypto in detail' })).toBeTruthy()
    expect(screen.getByText('Semiconductors')).toBeTruthy()
    // The Technology header reads the mention-weighted lean of NVDA + AMD.
    expect(screen.getByRole('button', { name: 'Show Technology in detail' }).textContent).toContain('Bullish · 60')
  })

  it('drills into a group and back', () => {
    const base = { sentiment_label_24h: 'NEUTRAL', price_direction: null, avg_sentiment_24h: 0, asset_kind: 'EQUITY' } as const
    mockUseMentionHeat.mockReturnValue({
      data: [
        { ...base, ticker: 'NVDA', mentions: 40, sector: 'Technology' },
        { ...base, ticker: 'XOM', mentions: 30, sector: 'Energy' },
      ],
      loading: false,
      error: false,
    })
    render(<MentionHeatmap assetKind="all" />)
    fireEvent.click(screen.getByRole('button', { name: 'Show Energy in detail' }))
    expect(screen.getAllByTestId('mention-heat-group')).toHaveLength(1)
    expect(screen.queryByText('$NVDA')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'All' }))
    expect(screen.getAllByTestId('mention-heat-group')).toHaveLength(2)
  })

  it('moves broad-market ETFs like SPY and QQQ into their own strip', () => {
    const base = { sentiment_label_24h: 'NEUTRAL', price_direction: null, avg_sentiment_24h: 0 } as const
    mockUseMentionHeat.mockReturnValue({
      data: [
        { ...base, ticker: 'SPY', mentions: 300, asset_kind: 'ETF' },
        { ...base, ticker: 'QQQ', mentions: 200, asset_kind: 'ETF' },
        { ...base, ticker: 'NVDA', mentions: 40, asset_kind: 'EQUITY', sector: 'Technology' },
      ],
      loading: false,
      error: false,
    })
    render(<MentionHeatmap assetKind="all" />)
    const strip = screen.getByTestId('mention-heat-broad-market')
    expect(strip.textContent).toContain('$SPY')
    expect(strip.textContent).toContain('$QQQ')
    const tiles = screen.getAllByTestId('mention-heat-tile').map(t => t.textContent)
    expect(tiles).toHaveLength(1)
    expect(tiles[0]).toContain('NVDA')
  })

  it('passes tile clicks through to onTickerClick', () => {
    mockUseMentionHeat.mockReturnValue({ data: sampleCells, loading: false, error: false })
    const onTickerClick = vi.fn()
    render(<MentionHeatmap assetKind="all" onTickerClick={onTickerClick} />)
    fireEvent.click(screen.getAllByTestId('mention-heat-tile')[0])
    expect(onTickerClick).toHaveBeenCalledWith('AAPL')
  })
})
