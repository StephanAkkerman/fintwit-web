import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RedditSection from '../components/RedditSection'

function mockFetch() {
  return vi.fn((url: string) => {
    if (url.startsWith('/api/reddit/trends')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          available: true,
          captured_at: new Date().toISOString(),
          subreddits: ['wallstreetbets'],
          tickers: [
            {
              symbol: 'NVDA',
              rank: 0,
              mentions: 12,
              previous_mentions: 5,
              unique_authors: 8,
              engagement: 340,
              mentions_per_hour: 0.5,
              momentum: 0.7,
              change_ratio: 1.4,
              spike_score: 1.1,
              heat_score: 0.6,
              sentiment: 'bullish',
              sentiment_score: 0.3,
              sentiment_breakdown: { bullish: 8 },
              is_emerging: false,
              subreddits: { wallstreetbets: 12 },
              sample_posts: [],
            },
          ],
        }),
      } as Response)
    }
    if (url.startsWith('/api/reddit/categories')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          available: true,
          default: ['wallstreetbets', 'stocks'],
          categories: {},
        }),
      } as Response)
    }
    return Promise.resolve({ ok: true, json: async () => [] } as Response)
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', mockFetch())
})

describe('RedditSection', () => {
  it('defaults to the Trends tab with no subreddit filter shown', async () => {
    render(<RedditSection />)

    await waitFor(() => expect(screen.getByText('Reddit Trends')).toBeInTheDocument())
    expect(screen.queryByLabelText(/subreddit/i)).not.toBeInTheDocument()
  })

  it('switches to Posts and defaults the subreddit filter to WallStreetBets', async () => {
    render(<RedditSection />)
    await waitFor(() => expect(screen.getByText('Reddit Trends')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('tab', { name: /posts/i }))

    await waitFor(() => expect(screen.getByText(/wallstreetbets radar/i)).toBeInTheDocument())
    expect(screen.getByRole('combobox')).toHaveValue('wallstreetbets')
  })

  it('re-fetches posts for the subreddit selected in the filter', async () => {
    const fetchMock = mockFetch()
    vi.stubGlobal('fetch', fetchMock)

    render(<RedditSection />)
    fireEvent.click(screen.getByRole('tab', { name: /posts/i }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/reddit/wsb'),
        expect.anything()
      )
    )
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('subreddit=wallstreetbets'),
        expect.anything()
      )
    )

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'stocks' } })

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('subreddit=stocks'),
        expect.anything()
      )
    )
  })
})
