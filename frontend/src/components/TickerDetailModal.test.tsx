import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TickerDetailModal from './TickerDetailModal'
import type { TickerTimeseries } from '../types'

vi.mock('../hooks/useTickerTimeseries', () => ({
  useTickerTimeseries: vi.fn(),
}))

import { useTickerTimeseries } from '../hooks/useTickerTimeseries'
const mockUseTickerTimeseries = vi.mocked(useTickerTimeseries)

const SAMPLE: TickerTimeseries = {
  ticker: 'AAPL',
  window_hours: 168,
  bucket_hours: 6,
  points: [
    { bucket: '2026-01-01T00:00:00Z', mentions: 3, bullish: 2, bearish: 1, neutral: 0, avg_sentiment: 0.2 },
    { bucket: '2026-01-02T00:00:00Z', mentions: 5, bullish: 1, bearish: 4, neutral: 0, avg_sentiment: -0.3 },
  ],
  summary: {
    total_mentions: 8,
    avg_mentions_per_bucket: 4,
    bullish: 3,
    bearish: 5,
    neutral: 0,
    avg_sentiment: -0.1,
    sentiment_label: 'BEAR',
    unique_authors: 4,
    chart_mentions: 2,
    avg_engagement: 42,
    asset_kind: 'EQUITY',
    price_direction: -2.5,
    first_seen: '2026-01-01T00:00:00Z',
    last_seen: '2026-01-07T00:00:00Z',
  },
}

const onClose = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
})

describe('TickerDetailModal', () => {
  it('shows a loading skeleton while fetching', () => {
    mockUseTickerTimeseries.mockReturnValue({ data: null, loading: true, error: false })
    render(<TickerDetailModal ticker="AAPL" onClose={onClose} />)
    expect(document.querySelector('.animate-pulse')).not.toBeNull()
  })

  it('surfaces an error message on failure', () => {
    mockUseTickerTimeseries.mockReturnValue({ data: null, loading: false, error: true })
    render(<TickerDetailModal ticker="AAPL" onClose={onClose} />)
    expect(screen.getByText(/failed to load \$AAPL details/i)).toBeInTheDocument()
  })

  it('shows an empty state when there are no mentions in the window', () => {
    mockUseTickerTimeseries.mockReturnValue({
      data: { ...SAMPLE, summary: { ...SAMPLE.summary, total_mentions: 0 } },
      loading: false,
      error: false,
    })
    render(<TickerDetailModal ticker="AAPL" onClose={onClose} />)
    expect(screen.getByText(/no \$AAPL mentions/i)).toBeInTheDocument()
  })

  it('renders summary stats when data is loaded', () => {
    mockUseTickerTimeseries.mockReturnValue({ data: SAMPLE, loading: false, error: false })
    render(<TickerDetailModal ticker="AAPL" onClose={onClose} />)

    expect(screen.getByText('$AAPL')).toBeInTheDocument()
    expect(screen.getByText('8')).toBeInTheDocument() // total mentions
    expect(screen.getByText('4.0')).toBeInTheDocument() // avg mentions/bucket
    expect(screen.getByText(/BEAR/)).toBeInTheDocument()
    expect(screen.getByText('-2.50%')).toBeInTheDocument()
  })

  it('calls onClose when the close button is clicked', () => {
    mockUseTickerTimeseries.mockReturnValue({ data: SAMPLE, loading: false, error: false })
    render(<TickerDetailModal ticker="AAPL" onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: /close ticker details/i }))
    expect(onClose).toHaveBeenCalled()
  })

  it('calls onClose when clicking the backdrop', () => {
    mockUseTickerTimeseries.mockReturnValue({ data: SAMPLE, loading: false, error: false })
    render(<TickerDetailModal ticker="AAPL" onClose={onClose} />)

    fireEvent.click(screen.getByRole('dialog'))
    expect(onClose).toHaveBeenCalled()
  })

  it('switches the requested window when a range button is clicked', () => {
    mockUseTickerTimeseries.mockReturnValue({ data: SAMPLE, loading: false, error: false })
    render(<TickerDetailModal ticker="AAPL" onClose={onClose} />)

    fireEvent.click(screen.getByRole('button', { name: '30d' }))
    expect(mockUseTickerTimeseries).toHaveBeenLastCalledWith('AAPL', 720)
  })
})
