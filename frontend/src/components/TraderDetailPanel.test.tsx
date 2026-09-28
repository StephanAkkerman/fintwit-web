import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TraderDetailPanel from './TraderDetailPanel'
import type { TraderDetail } from '../types'

vi.mock('../hooks/useTraderDetail', () => ({
  useTraderDetail: vi.fn(),
}))

import { useTraderDetail } from '../hooks/useTraderDetail'
const mockUseTraderDetail = vi.mocked(useTraderDetail)

const DETAIL: TraderDetail = {
  user_screen_name: 'finguru',
  horizon_days: 7,
  summary: {
    total_calls: 3,
    bullish_calls: 2,
    bearish_calls: 1,
    distinct_tickers: 2,
    first_called_at: '2026-09-01 10:00:00',
    last_called_at: '2026-09-20 10:00:00',
  },
  horizons: [
    { horizon_days: 1, graded_calls: 2, correct_calls: 1, hit_rate: 0.5, avg_return_pct: 0.4 },
    { horizon_days: 7, graded_calls: 2, correct_calls: 2, hit_rate: 1, avg_return_pct: 6.5 },
    { horizon_days: 30, graded_calls: 0, correct_calls: 0, hit_rate: null, avg_return_pct: null },
  ],
  tickers: [
    {
      ticker: 'NVDA',
      asset_kind: 'EQUITY',
      calls: 2,
      bullish_calls: 1,
      bearish_calls: 1,
      last_called_at: '2026-09-20 10:00:00',
      graded_calls: 1,
      correct_calls: 1,
      hit_rate: 1,
      avg_return_pct: 8,
    },
  ],
  recent_calls: [
    {
      id: 3,
      tweet_id: 3,
      ticker: 'NVDA',
      direction: 'bearish',
      sentiment_score: -0.7,
      asset_kind: 'EQUITY',
      price_at_call: 120,
      called_at: '2026-09-20 10:00:00',
      tweet_text: 'Fading $NVDA into earnings',
      tweet_url: 'https://x.com/finguru/status/3',
      results: [
        {
          horizon_days: 7,
          price_at_horizon: 110.4,
          return_pct: -8,
          correct: true,
          excluded: false,
          evaluated_at: '2026-09-27 10:00:00',
        },
      ],
    },
    {
      id: 2,
      tweet_id: 2,
      ticker: 'PEPE',
      direction: 'bullish',
      sentiment_score: 0.8,
      asset_kind: 'CRYPTO',
      price_at_call: 0.00001,
      called_at: '2026-09-10 10:00:00',
      tweet_text: null,
      tweet_url: null,
      results: [
        {
          horizon_days: 7,
          price_at_horizon: 250,
          return_pct: 2_499_999_900,
          correct: true,
          excluded: true,
          evaluated_at: '2026-09-17 10:00:00',
        },
      ],
    },
  ],
}

describe('TraderDetailPanel', () => {
  beforeEach(() => {
    mockUseTraderDetail.mockReset()
  })

  it('shows a loading skeleton before the first payload', () => {
    mockUseTraderDetail.mockReturnValue({ data: null, loading: true, error: false })
    const { container } = render(<TraderDetailPanel screenName="finguru" horizon={7} onClose={() => {}} />)
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })

  it('shows an empty state for a trader with no calls', () => {
    mockUseTraderDetail.mockReturnValue({
      data: { ...DETAIL, tickers: [], recent_calls: [] },
      loading: false,
      error: false,
    })
    render(<TraderDetailPanel screenName="nobody" horizon={7} onClose={() => {}} />)
    expect(screen.getByText('No calls recorded for @nobody yet.')).toBeInTheDocument()
  })

  it('signs a bearish call by direction and marks an excluded result as not scored', () => {
    mockUseTraderDetail.mockReturnValue({ data: DETAIL, loading: false, error: false })
    render(<TraderDetailPanel screenName="finguru" horizon={7} onClose={() => {}} />)

    // A bearish call on a -8% move made +8%.
    expect(screen.getByText('7d +8.0%')).toBeInTheDocument()
    // The mismatched PEPE result is shown as n/a, never as a giant return.
    expect(screen.getAllByText('7d n/a').length).toBe(1)
    expect(screen.queryByText(/2499999900|2,499,999,900/)).not.toBeInTheDocument()
    expect(screen.getByText('Fading $NVDA into earnings')).toBeInTheDocument()
  })

  it('opens the ticker modal from the breakdown and closes via the button', () => {
    mockUseTraderDetail.mockReturnValue({ data: DETAIL, loading: false, error: false })
    const onTickerClick = vi.fn()
    const onClose = vi.fn()
    render(
      <TraderDetailPanel screenName="finguru" horizon={7} onClose={onClose} onTickerClick={onTickerClick} />
    )

    fireEvent.click(screen.getAllByRole('button', { name: '$NVDA' })[0])
    expect(onTickerClick).toHaveBeenCalledWith('NVDA')

    fireEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalled()
  })
})
