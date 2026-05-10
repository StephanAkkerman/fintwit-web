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
    avg_sentiment_24h: 0.8,
    avg_sentiment_prev: 0.5,
    delta: 0.3,
    sentiment_label_24h: 'BULL' as const,
    sentiment_label_prev: 'BULL' as const,
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

  it('renders one row per item with ticker and signed delta', () => {
    const items = makeSample(3)
    mockUseSentimentShift.mockReturnValue({ data: items, loading: false, error: false })
    render(<SentimentShiftWidget assetKind="EQUITY" />)

    expect(screen.getByText('Sentiment Shift')).toBeTruthy()
    expect(screen.getByText('TKR0')).toBeTruthy()
    expect(screen.getByText('TKR1')).toBeTruthy()
    expect(screen.getByText('TKR2')).toBeTruthy()

    // prev→current arrow is embedded in the text node with surrounding values
    const cells = document.querySelectorAll('[class*="text-zinc-500"]')
    const arrowCells = [...cells].filter(el => el.textContent?.includes('→'))
    expect(arrowCells.length).toBe(3)

    // Each row shows the formatted delta (▲ +0.30)
    const deltas = screen.getAllByText(/▲\s*\+0\.30/)
    expect(deltas.length).toBe(3)
  })

  it('renders all returned items without client-side truncation', () => {
    // Backend already caps at top N — widget renders whatever comes back.
    const items = makeSample(13)
    mockUseSentimentShift.mockReturnValue({ data: items, loading: false, error: false })
    render(<SentimentShiftWidget assetKind="all" />)

    expect(screen.getByText('TKR0')).toBeTruthy()
    expect(screen.getByText('TKR12')).toBeTruthy()
  })
})
