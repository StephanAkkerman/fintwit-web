import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RedditTrendsWidget } from '../components/RedditTrendsWidget'

function ticker(overrides: Record<string, unknown> = {}) {
  return {
    symbol: 'NVDA',
    rank: 0,
    mentions: 41,
    previous_mentions: 18,
    unique_authors: 33,
    engagement: 1320,
    mentions_per_hour: 1.7,
    momentum: 1.21,
    change_ratio: 2.28,
    spike_score: 2.84,
    heat_score: 0.912,
    sentiment: 'bullish',
    sentiment_score: 0.44,
    sentiment_breakdown: { bullish: 30 },
    is_emerging: false,
    subreddits: { wallstreetbets: 30 },
    sample_posts: [],
    ...overrides,
  }
}

function mockResponse(payload: Record<string, unknown>) {
  const fetchMock = vi.fn(() =>
    Promise.resolve({ ok: true, json: async () => payload } as Response)
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

beforeEach(() => {
  vi.unstubAllGlobals()
})

describe('RedditTrendsWidget', () => {
  it('renders the ranked tickers with mentions and momentum', async () => {
    mockResponse({
      available: true,
      captured_at: new Date().toISOString(),
      subreddits: ['wallstreetbets', 'stocks'],
      tickers: [ticker(), ticker({ symbol: 'INTC', mentions: 9, momentum: -0.4, sentiment: 'bearish', sentiment_score: -0.51 })],
    })

    render(<RedditTrendsWidget />)

    expect(await screen.findByText('Reddit Trends')).toBeInTheDocument()
    expect(screen.getByText('NVDA')).toBeInTheDocument()
    expect(screen.getByText('INTC')).toBeInTheDocument()
    // mentions now/prev, so a reader can see the comparison the rank is built on
    expect(screen.getByText('41')).toBeInTheDocument()
    // The momentum cell carries its arrow in the same node ("▲ +1.21").
    expect(screen.getByText(/\+1\.21/)).toBeInTheDocument()
    expect(screen.getByText(/-0\.40/)).toBeInTheDocument()
  })

  it('keeps a bearish ticker negative', async () => {
    mockResponse({
      available: true,
      captured_at: new Date().toISOString(),
      subreddits: ['stocks'],
      tickers: [ticker({ symbol: 'INTC', sentiment: 'bearish', sentiment_score: -0.51 })],
    })

    render(<RedditTrendsWidget />)

    expect(await screen.findByText('-0.51')).toBeInTheDocument()
  })

  it('flags an emerging ticker', async () => {
    mockResponse({
      available: true,
      captured_at: new Date().toISOString(),
      subreddits: ['wallstreetbets'],
      tickers: [ticker({ symbol: 'RKLB', is_emerging: true, previous_mentions: 0 })],
      emerging: ['RKLB'],
    })

    render(<RedditTrendsWidget />)

    expect(await screen.findByText('NEW')).toBeInTheDocument()
    expect(screen.getByText(/emerging: RKLB/)).toBeInTheDocument()
  })

  it('says so when the analyzer package is not installed', async () => {
    mockResponse({ available: false, captured_at: null, subreddits: [], tickers: [] })

    render(<RedditTrendsWidget />)

    expect(await screen.findByText(/not enabled in this deployment/)).toBeInTheDocument()
  })

  it('distinguishes "not scraped yet" from "not installed"', async () => {
    mockResponse({ available: true, captured_at: null, subreddits: ['wallstreetbets'], tickers: [] })

    render(<RedditTrendsWidget />)

    expect(await screen.findByText(/Waiting for the first Reddit scrape/)).toBeInTheDocument()
  })

  it('shows the worker error instead of waiting forever when the scrape fails', async () => {
    mockResponse({
      available: true,
      captured_at: null,
      subreddits: ['wallstreetbets'],
      tickers: [],
      worker: {
        state: 'error',
        last_error: 'ImportError: gliner2 needs transformers<5',
        last_attempt_at: new Date().toISOString(),
        next_attempt_at: new Date(Date.now() + 120_000).toISOString(),
      },
    })

    render(<RedditTrendsWidget />)

    expect(await screen.findByText(/scrape is failing/)).toBeInTheDocument()
    expect(screen.getByText(/gliner2 needs transformers<5/)).toBeInTheDocument()
    expect(screen.getByText(/retrying in 2m/)).toBeInTheDocument()
    expect(screen.queryByText(/Waiting for the first/)).not.toBeInTheDocument()
  })

  it('says when Reddit returned no posts', async () => {
    mockResponse({
      available: true,
      captured_at: null,
      subreddits: ['wallstreetbets'],
      tickers: [],
      worker: { state: 'empty', last_error: 'Set REDDIT_CLIENT_ID to scrape authenticated.' },
    })

    render(<RedditTrendsWidget />)

    expect(await screen.findByText(/last Reddit scrape returned no posts/)).toBeInTheDocument()
    expect(screen.getByText(/REDDIT_CLIENT_ID/)).toBeInTheDocument()
  })

  it('says the models are still loading during warm-up', async () => {
    mockResponse({
      available: true,
      captured_at: null,
      subreddits: [],
      tickers: [],
      worker: { state: 'warming_up' },
    })

    render(<RedditTrendsWidget />)

    expect(await screen.findByText(/Loading the ticker and sentiment models/)).toBeInTheDocument()
  })

  it('flags a failing refresh over an older run', async () => {
    mockResponse({
      available: true,
      captured_at: new Date(Date.now() - 3 * 3600_000).toISOString(),
      subreddits: ['wallstreetbets'],
      tickers: [ticker()],
      worker: { state: 'error', last_error: 'HTTPError: 403' },
    })

    render(<RedditTrendsWidget />)

    expect(await screen.findByText(/Refresh failing/)).toBeInTheDocument()
    expect(screen.getByText('HTTPError: 403')).toBeInTheDocument()
    expect(screen.getByText('NVDA')).toBeInTheDocument()
  })

  it('draws an hourly sparkline for tickers in the timeline', async () => {
    mockResponse({
      available: true,
      captured_at: new Date().toISOString(),
      subreddits: ['wallstreetbets'],
      tickers: [ticker(), ticker({ symbol: 'AMD' })],
      timeline: { bucket_seconds: 3600, series: { NVDA: [0, 2, 5, 3] } },
    })

    render(<RedditTrendsWidget />)

    await screen.findByText('NVDA')
    expect(screen.getAllByTestId('reddit-sparkline')).toHaveLength(1)
  })

  it('renders no stray 0 when nothing is emerging or fading', async () => {
    mockResponse({
      available: true,
      captured_at: new Date().toISOString(),
      subreddits: ['wallstreetbets'],
      tickers: [ticker()],
      emerging: [],
      fading: [],
    })

    const { container } = render(<RedditTrendsWidget />)

    await screen.findByText('NVDA')
    expect(screen.queryByText(/emerging:/)).not.toBeInTheDocument()
    expect(container.textContent?.trim().endsWith('0')).toBe(false)
  })

  it('handles a run that recognised no tickers', async () => {
    mockResponse({
      available: true,
      captured_at: new Date().toISOString(),
      subreddits: ['wallstreetbets'],
      tickers: [],
    })

    render(<RedditTrendsWidget />)

    expect(await screen.findByText(/No tickers recognised/)).toBeInTheDocument()
  })

  it('shows an error state when the request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: false, json: async () => ({}) } as Response))
    )

    render(<RedditTrendsWidget />)

    await waitFor(() =>
      expect(screen.getByText(/Failed to load Reddit trends/)).toBeInTheDocument()
    )
  })

  it('requests the configured number of tickers', async () => {
    const fetchMock = mockResponse({
      available: true,
      captured_at: new Date().toISOString(),
      subreddits: [],
      tickers: [],
    })

    render(<RedditTrendsWidget limit={5} />)

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/reddit/trends?limit=5',
        expect.anything()
      )
    )
  })
})
