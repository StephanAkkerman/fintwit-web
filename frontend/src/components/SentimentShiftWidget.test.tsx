import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { SentimentShiftWidget } from './SentimentShiftWidget'
import type { SentimentShiftItem } from '../types'

vi.mock('../hooks/useSentimentShift', () => ({
  useSentimentShift: vi.fn(),
}))

import { useSentimentShift } from '../hooks/useSentimentShift'
const mockUseSentimentShift = vi.mocked(useSentimentShift)

const makeSample = (n: number): SentimentShiftItem[] =>
  Array.from({ length: n }, (_, i) => ({
    ticker: `TKR${i}`,
    mentions_24h: 10 + i,
    sentiment_label_24h: 'BULL' as const,
    sentiment_label_prev: 'BEAR' as const,
    asset_kind: 'EQUITY',
  }))

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SentimentShiftWidget', () => {
  it('shows loading skeleton when loading is true', () => {
    mockUseSentimentShift.mockReturnValue({ data: [], loading: true, error: false })
    render(<SentimentShiftWidget assetKind="all" />)
    const skeleton = document.querySelector('.animate-pulse')
    expect(skeleton).not.toBeNull()
  })

  it('shows error message when error is true', () => {
    mockUseSentimentShift.mockReturnValue({ data: [], loading: false, error: true })
    render(<SentimentShiftWidget assetKind="all" />)
    expect(screen.getByText(/Failed to load sentiment data/i)).toBeTruthy()
  })

  it('shows empty state when data is empty and loading is false', () => {
    mockUseSentimentShift.mockReturnValue({ data: [], loading: false, error: false })
    render(<SentimentShiftWidget assetKind="all" />)
    expect(screen.getByText(/No sentiment shift data/i)).toBeTruthy()
  })

  it('renders rows with ticker, prev badge, arrow, and now badge', () => {
    const items = makeSample(3)
    mockUseSentimentShift.mockReturnValue({ data: items, loading: false, error: false })
    render(<SentimentShiftWidget assetKind="EQUITY" />)

    // Header
    expect(screen.getByText('Sentiment Shift')).toBeTruthy()

    // Tickers
    expect(screen.getByText('TKR0')).toBeTruthy()
    expect(screen.getByText('TKR1')).toBeTruthy()
    expect(screen.getByText('TKR2')).toBeTruthy()

    // Arrows (one per row)
    const arrows = screen.getAllByText('→')
    expect(arrows.length).toBe(3)

    // Badges — each row has BEAR (prev) → BULL (now)
    const bullBadges = screen.getAllByText('BULL')
    const bearBadges = screen.getAllByText('BEAR')
    expect(bullBadges.length).toBe(3)
    expect(bearBadges.length).toBe(3)
  })

  it('truncates to 10 rows and shows "+N more" when data has >10 items', () => {
    const items = makeSample(13)
    mockUseSentimentShift.mockReturnValue({ data: items, loading: false, error: false })
    render(<SentimentShiftWidget assetKind="all" />)

    // Only first 10 tickers should be visible
    expect(screen.getByText('TKR0')).toBeTruthy()
    expect(screen.getByText('TKR9')).toBeTruthy()
    expect(screen.queryByText('TKR10')).toBeNull()

    // "+3 more" truncation label
    expect(screen.getByText('+3 more')).toBeTruthy()
  })
})
