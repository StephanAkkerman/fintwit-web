import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TickerDetailModal from './TickerDetailModal'
import type { TickerPriceHistory, TickerTimeseries } from '../types'

vi.mock('../hooks/useTickerTimeseries', () => ({
  useTickerTimeseries: vi.fn(),
}))
vi.mock('../hooks/useTickerPriceHistory', () => ({
  useTickerPriceHistory: vi.fn(),
}))

import { useTickerPriceHistory } from '../hooks/useTickerPriceHistory'
import { useTickerTimeseries } from '../hooks/useTickerTimeseries'
const mockUseTickerTimeseries = vi.mocked(useTickerTimeseries)
const mockUseTickerPriceHistory = vi.mocked(useTickerPriceHistory)

const SAMPLE_PRICE_HISTORY: TickerPriceHistory = {
  ticker: 'AAPL',
  points: [
    { t: '2026-01-07T14:30:00Z', close: 184.0, high: 184.5, low: 183.5 },
    { t: '2026-01-07T14:35:00Z', close: 185.0, high: 185.5, low: 184.0 },
    { t: '2026-01-07T14:40:00Z', close: 186.4, high: 186.8, low: 185.2 },
  ],
}

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
  mockUseTickerPriceHistory.mockReturnValue({
    data: SAMPLE_PRICE_HISTORY,
    loading: false,
    error: false,
  })
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

  it('renders the price change badge from the fetched intraday series', () => {
    mockUseTickerTimeseries.mockReturnValue({ data: SAMPLE, loading: false, error: false })
    render(<TickerDetailModal ticker="AAPL" onClose={onClose} />)

    // (186.4 - 184.0) / 184.0 * 100
    expect(screen.getByText('+1.30%')).toBeInTheDocument()
  })

  it('colors the price badge with the exact color the chart line uses, not a separate Tailwind shade', () => {
    mockUseTickerTimeseries.mockReturnValue({ data: SAMPLE, loading: false, error: false })
    render(<TickerDetailModal ticker="AAPL" onClose={onClose} />)

    const badge = screen.getByText('+1.30%')
    // rgb(52, 211, 153) is #34d399, the same hex Sparkline.tsx uses for "up".
    // Tailwind's text-emerald-600/dark:text-emerald-400 classes render a
    // visibly different shade than that fixed chart-line color.
    expect(badge).toHaveStyle({ color: 'rgb(52, 211, 153)' })
    expect(badge.className).not.toMatch(/text-emerald|text-rose/)
  })

  it('colors the badge red to match a declining line', () => {
    mockUseTickerPriceHistory.mockReturnValue({
      data: {
        ticker: 'AAPL',
        points: [
          { t: '2026-01-07T14:30:00Z', close: 186.0, high: 186.4, low: 185.5 },
          { t: '2026-01-07T14:35:00Z', close: 184.0, high: 184.5, low: 183.5 },
        ],
      },
      loading: false,
      error: false,
    })
    mockUseTickerTimeseries.mockReturnValue({ data: SAMPLE, loading: false, error: false })
    render(<TickerDetailModal ticker="AAPL" onClose={onClose} />)

    const badge = screen.getByText(/-1\.08%/)
    // rgb(251, 113, 133) is #fb7185, the same hex Sparkline.tsx uses for "down".
    expect(badge).toHaveStyle({ color: 'rgb(251, 113, 133)' })
  })

  it('shows a loading skeleton for the price chart while it fetches', () => {
    mockUseTickerTimeseries.mockReturnValue({ data: SAMPLE, loading: false, error: false })
    mockUseTickerPriceHistory.mockReturnValue({ data: null, loading: true, error: false })
    render(<TickerDetailModal ticker="AAPL" onClose={onClose} />)

    expect(document.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })

  it('shows an empty state when no intraday price data is available', () => {
    mockUseTickerTimeseries.mockReturnValue({ data: SAMPLE, loading: false, error: false })
    mockUseTickerPriceHistory.mockReturnValue({
      data: { ticker: 'AAPL', points: [] },
      loading: false,
      error: false,
    })
    render(<TickerDetailModal ticker="AAPL" onClose={onClose} />)

    expect(screen.getByText(/no intraday price data available/i)).toBeInTheDocument()
  })

  it('still renders the price chart when there are no mentions', () => {
    mockUseTickerTimeseries.mockReturnValue({
      data: { ...SAMPLE, summary: { ...SAMPLE.summary, total_mentions: 0 } },
      loading: false,
      error: false,
    })
    render(<TickerDetailModal ticker="AAPL" onClose={onClose} />)

    expect(screen.getByText(/no \$AAPL mentions/i)).toBeInTheDocument()
    expect(screen.getByText('+1.30%')).toBeInTheDocument()
  })
})
