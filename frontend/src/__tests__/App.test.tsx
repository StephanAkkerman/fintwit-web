import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import type { Tweet } from '../types'

// Stub fetch and EventSource so the hook doesn't throw in jsdom
class MockEventSource {
  onmessage: null = null
  onerror: null = null
  close = vi.fn()
  constructor(_url: string, _init?: EventSourceInit) {}
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  vi.stubGlobal('EventSource', MockEventSource)
  fetchMock = vi.fn((input: string | URL | Request) => {
    const url = String(input)
    if (url.includes('/api/posts')) {
      return Promise.resolve({ ok: true, json: async () => [] } as Response)
    }
    if (url.includes('/api/fear-greed')) {
      return Promise.resolve(
        {
          ok: true,
          json: async () => ({ value: 50, change: '+0', status: 'Neutral' }),
        } as Response
      )
    }
    return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
  })
  vi.stubGlobal('fetch', fetchMock)
})

describe('App', () => {
  it('renders the X Stream heading', async () => {
    render(<App />)
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /x stream/i })).toBeInTheDocument()
    )
  })

  it('renders the live tweets subtitle', async () => {
    render(<App />)
    await waitFor(() =>
      expect(screen.getByText(/live tweets/i)).toBeInTheDocument()
    )
  })

  it('filters by crypto, stock, and non-financial categories', async () => {
    const posts: Tweet[] = [
      {
        id: 1,
        text: '$BTC breakout',
        user_name: 'Crypto User',
        user_screen_name: 'crypto_user',
        user_img: 'https://example.com/c.jpg',
        url: 'https://x.com/crypto_user/status/1',
        created_at: '',
        media: [],
        tickers: ['BTC'],
        hashtags: [],
        title: '',
        media_types: [],
        replies: 0,
        likes: 0,
        views: 0,
        retweets: 0,
        assets: [{ symbol: 'BTC', kind: 'crypto' }],
      },
      {
        id: 2,
        text: '$AAPL earnings',
        user_name: 'Stock User',
        user_screen_name: 'stock_user',
        user_img: 'https://example.com/s.jpg',
        url: 'https://x.com/stock_user/status/2',
        created_at: '',
        media: [],
        tickers: ['AAPL'],
        hashtags: [],
        title: '',
        media_types: [],
        replies: 0,
        likes: 0,
        views: 0,
        retweets: 0,
        assets: [{ symbol: 'AAPL', kind: 'EQUITY' }],
      },
      {
        id: 3,
        text: 'Just chatting about weekend plans',
        user_name: 'General User',
        user_screen_name: 'general_user',
        user_img: 'https://example.com/g.jpg',
        url: 'https://x.com/general_user/status/3',
        created_at: '',
        media: [],
        tickers: [],
        hashtags: [],
        title: '',
        media_types: [],
        replies: 0,
        likes: 0,
        views: 0,
        retweets: 0,
        assets: [],
      },
    ]

    fetchMock.mockImplementation((input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('/api/posts')) {
        return Promise.resolve({ ok: true, json: async () => posts } as Response)
      }
      if (url.includes('/api/fear-greed')) {
        return Promise.resolve(
          {
            ok: true,
            json: async () => ({ value: 50, change: '+0', status: 'Neutral' }),
          } as Response
        )
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('Crypto User')).toBeInTheDocument()
      expect(screen.getByText('Stock User')).toBeInTheDocument()
      expect(screen.getByText('General User')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /crypto/i }))
    await waitFor(() => {
      expect(screen.getByText('Crypto User')).toBeInTheDocument()
      expect(screen.queryByText('Stock User')).not.toBeInTheDocument()
      expect(screen.queryByText('General User')).not.toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /stock/i }))
    await waitFor(() => {
      expect(screen.getByText('Stock User')).toBeInTheDocument()
      expect(screen.queryByText('Crypto User')).not.toBeInTheDocument()
      expect(screen.queryByText('General User')).not.toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /non-financial/i }))
    await waitFor(() => {
      expect(screen.getByText('General User')).toBeInTheDocument()
      expect(screen.queryByText('Crypto User')).not.toBeInTheDocument()
      expect(screen.queryByText('Stock User')).not.toBeInTheDocument()
    })
  })

  it('filters tweets by ticker when a financial ticker is clicked', async () => {
    const posts: Tweet[] = [
      {
        id: 1,
        text: '$AAPL earnings',
        user_name: 'Stock User',
        user_screen_name: 'stock_user',
        user_img: 'https://example.com/s.jpg',
        url: 'https://x.com/stock_user/status/1',
        created_at: '',
        media: [],
        tickers: ['AAPL'],
        hashtags: [],
        title: '',
        media_types: [],
        replies: 0,
        likes: 0,
        views: 0,
        retweets: 0,
        assets: [{ symbol: 'AAPL', kind: 'EQUITY', financials: { price: 185.12, change_percent: 1.2 } }],
      },
      {
        id: 2,
        text: '$BTC breakout',
        user_name: 'Crypto User',
        user_screen_name: 'crypto_user',
        user_img: 'https://example.com/c.jpg',
        url: 'https://x.com/crypto_user/status/2',
        created_at: '',
        media: [],
        tickers: ['BTC'],
        hashtags: [],
        title: '',
        media_types: [],
        replies: 0,
        likes: 0,
        views: 0,
        retweets: 0,
        assets: [{ symbol: 'BTC', kind: 'crypto', financials: { price: 68000, change_percent: 2.0 } }],
      },
    ]

    fetchMock.mockImplementation((input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('/api/posts')) {
        return Promise.resolve({ ok: true, json: async () => posts } as Response)
      }
      if (url.includes('/api/fear-greed')) {
        return Promise.resolve(
          {
            ok: true,
            json: async () => ({ value: 50, change: '+0', status: 'Neutral' }),
          } as Response
        )
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('Stock User')).toBeInTheDocument()
      expect(screen.getByText('Crypto User')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Filter by $AAPL' }))

    await waitFor(() => {
      expect(screen.getByText('Stock User')).toBeInTheDocument()
      expect(screen.queryByText('Crypto User')).not.toBeInTheDocument()
    })
  })

  it('filters tweets by typed ticker input', async () => {
    const posts: Tweet[] = [
      {
        id: 1,
        text: '$SOL update',
        user_name: 'Sol User',
        user_screen_name: 'sol_user',
        user_img: 'https://example.com/sol.jpg',
        url: 'https://x.com/sol_user/status/1',
        created_at: '',
        media: [],
        tickers: ['SOL'],
        hashtags: [],
        title: '',
        media_types: [],
        replies: 0,
        likes: 0,
        views: 0,
        retweets: 0,
        assets: [{ symbol: 'SOL', kind: 'crypto', financials: { price: 130.0, change_percent: 1.1 } }],
      },
      {
        id: 2,
        text: '$AAPL move',
        user_name: 'Apple User',
        user_screen_name: 'apple_user',
        user_img: 'https://example.com/aapl.jpg',
        url: 'https://x.com/apple_user/status/2',
        created_at: '',
        media: [],
        tickers: ['AAPL'],
        hashtags: [],
        title: '',
        media_types: [],
        replies: 0,
        likes: 0,
        views: 0,
        retweets: 0,
        assets: [{ symbol: 'AAPL', kind: 'EQUITY', financials: { price: 185.0, change_percent: 0.5 } }],
      },
    ]

    fetchMock.mockImplementation((input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('/api/posts')) {
        return Promise.resolve({ ok: true, json: async () => posts } as Response)
      }
      if (url.includes('/api/fear-greed')) {
        return Promise.resolve(
          {
            ok: true,
            json: async () => ({ value: 50, change: '+0', status: 'Neutral' }),
          } as Response
        )
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('Sol User')).toBeInTheDocument()
      expect(screen.getByText('Apple User')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Ticker symbol'), { target: { value: '$sol' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))

    await waitFor(() => {
      expect(screen.getByText('Sol User')).toBeInTheDocument()
      expect(screen.queryByText('Apple User')).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Filter by $SOL' })).toBeInTheDocument()
    })
  })
})
