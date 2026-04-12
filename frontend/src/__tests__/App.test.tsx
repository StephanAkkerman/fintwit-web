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
  window.history.pushState({}, '', '/')
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
    if (url.includes('/api/reddit/wsb')) {
      return Promise.resolve({ ok: true, json: async () => [] } as Response)
    }
    if (url.includes('/api/trending-crypto')) {
      return Promise.resolve({ ok: true, json: async () => [] } as Response)
    }
    if (url.includes('/api/nfts/trending')) {
      return Promise.resolve({ ok: true, json: async () => [] } as Response)
    }
    if (url.includes('/api/treemap')) {
      return Promise.resolve({ ok: true, json: async () => ({ data: [] }) } as Response)
    }
    if (url.includes('/api/stocktwits')) {
      return Promise.resolve({ ok: true, json: async () => [] } as Response)
    }
    if (url.includes('/api/stocks/market-hours')) {
      return Promise.resolve({ ok: true, json: async () => [] } as Response)
    }
    if (url.includes('/api/spy-heatmap')) {
      return Promise.resolve({ ok: true, json: async () => ({ data: [] }) } as Response)
    }
    if (url.includes('/api/portfolio/positions')) {
      return Promise.resolve({ ok: true, json: async () => [] } as Response)
    }
    if (url.includes('/api/portfolio/summary')) {
      return Promise.resolve(
        {
          ok: true,
          json: async () => ({
            totals: {
              positions: 0,
              market_value: 0,
              cost_basis: 0,
              unrealized_pnl: 0,
              unrealized_pnl_percent: 0,
            },
            positions: [],
          }),
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

  it('renders the home subtitle', async () => {
    render(<App />)
    await waitFor(() =>
      expect(screen.getByText(/cross-market stream/i)).toBeInTheDocument()
    )
    expect(screen.getByText(/wallstreetbets radar/i)).toBeInTheDocument()
  })

  it('shows crypto section widgets when navigating to /crypto', async () => {
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'Open /crypto' }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /trending crypto/i })).toBeInTheDocument()
    )
    expect(screen.getByText(/top coins by market cap/i)).toBeInTheDocument()
    expect(window.location.pathname).toBe('/crypto')
  })

  it('shows stock section widgets when navigating to /stocks', async () => {
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'Open /stocks' }))

    await waitFor(() =>
      expect(screen.getByText(/stocktwits signals/i)).toBeInTheDocument()
    )
    expect(screen.getByText(/major exchange sessions/i)).toBeInTheDocument()
    expect(screen.getByText(/spy heatmap/i)).toBeInTheDocument()
    expect(window.location.pathname).toBe('/stocks')
  })

  it('shows nft section widget when navigating to /nfts', async () => {
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'Open /nfts' }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /trending nfts/i })).toBeInTheDocument()
    )
    expect(window.location.pathname).toBe('/nfts')
  })

  it('shows debug admin panel when navigating to /admin', async () => {
    fetchMock.mockImplementation((input: string | URL | Request) => {
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
      if (url.includes('/api/reddit/wsb')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/trending-crypto')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/treemap')) {
        return Promise.resolve({ ok: true, json: async () => ({ data: [] }) } as Response)
      }
      if (url.includes('/api/stocktwits')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/spy-heatmap')) {
        return Promise.resolve({ ok: true, json: async () => ({ data: [] }) } as Response)
      }
      if (url.includes('/api/debug/tweet')) {
        return Promise.resolve({ ok: true, json: async () => ({ id: 123, text: 'Debug tweet' }) } as Response)
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
    })

    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'Open /admin' }))

    await waitFor(() => {
      expect(screen.getByText(/debug admin panel/i)).toBeInTheDocument()
    })
    expect(window.location.pathname).toBe('/admin')
  })

  it('shows portfolio panel when navigating to /portfolio', async () => {
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'Open /portfolio' }))

    await waitFor(() => {
      expect(screen.getByText(/ibkr live positions/i)).toBeInTheDocument()
    })
    expect(window.location.pathname).toBe('/portfolio')
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
      if (url.includes('/api/reddit/wsb')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/trending-crypto')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/treemap')) {
        return Promise.resolve({ ok: true, json: async () => ({ data: [] }) } as Response)
      }
      if (url.includes('/api/stocktwits')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/spy-heatmap')) {
        return Promise.resolve({ ok: true, json: async () => ({ data: [] }) } as Response)
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('Crypto User')).toBeInTheDocument()
      expect(screen.getByText('Stock User')).toBeInTheDocument()
      expect(screen.getByText('General User')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Timeline filter Crypto' }))
    await waitFor(() => {
      expect(screen.getByText('Crypto User')).toBeInTheDocument()
      expect(screen.queryByText('Stock User')).not.toBeInTheDocument()
      expect(screen.queryByText('General User')).not.toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Timeline filter Stock' }))
    await waitFor(() => {
      expect(screen.getByText('Stock User')).toBeInTheDocument()
      expect(screen.queryByText('Crypto User')).not.toBeInTheDocument()
      expect(screen.queryByText('General User')).not.toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Timeline filter Non-financial' }))
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
      if (url.includes('/api/reddit/wsb')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/trending-crypto')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/treemap')) {
        return Promise.resolve({ ok: true, json: async () => ({ data: [] }) } as Response)
      }
      if (url.includes('/api/stocktwits')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/spy-heatmap')) {
        return Promise.resolve({ ok: true, json: async () => ({ data: [] }) } as Response)
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
      if (url.includes('/api/trending-crypto')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/treemap')) {
        return Promise.resolve({ ok: true, json: async () => ({ data: [] }) } as Response)
      }
      if (url.includes('/api/stocktwits')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/spy-heatmap')) {
        return Promise.resolve({ ok: true, json: async () => ({ data: [] }) } as Response)
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

  it('sorts and filters chart tweets in crypto route', async () => {
    const posts: Tweet[] = [
      {
        id: 1,
        text: '$BTC text-only signal',
        user_name: 'NoChart Crypto',
        user_screen_name: 'nochart_crypto',
        user_img: 'https://example.com/nc.jpg',
        url: 'https://x.com/nochart/status/1',
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
        has_chart: false,
        assets: [{ symbol: 'BTC', kind: 'crypto' }],
      },
      {
        id: 2,
        text: '$ETH with chart image',
        user_name: 'Chart Crypto',
        user_screen_name: 'chart_crypto',
        user_img: 'https://example.com/c.jpg',
        url: 'https://x.com/chart/status/2',
        created_at: '',
        media: [{ url: 'https://example.com/chart.png', type: 'photo' }],
        tickers: ['ETH'],
        hashtags: [],
        title: '',
        media_types: ['photo'],
        replies: 0,
        likes: 0,
        views: 0,
        retweets: 0,
        has_chart: true,
        assets: [{ symbol: 'ETH', kind: 'crypto' }],
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
      if (url.includes('/api/trending-crypto')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/treemap')) {
        return Promise.resolve({ ok: true, json: async () => ({ data: [] }) } as Response)
      }
      if (url.includes('/api/stocktwits')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/spy-heatmap')) {
        return Promise.resolve({ ok: true, json: async () => ({ data: [] }) } as Response)
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
    })

    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'Open /crypto' }))

    await waitFor(() => {
      expect(screen.getByText('NoChart Crypto')).toBeInTheDocument()
      expect(screen.getByText('Chart Crypto')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Chart sort Charts first' }))

    await waitFor(() => {
      const chartNode = screen.getByText('Chart Crypto')
      const plainNode = screen.getByText('NoChart Crypto')
      expect(Boolean(chartNode.compareDocumentPosition(plainNode) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
    })

    fireEvent.click(screen.getByRole('button', { name: 'Chart sort Charts only' }))

    await waitFor(() => {
      expect(screen.getByText('Chart Crypto')).toBeInTheDocument()
      expect(screen.queryByText('NoChart Crypto')).not.toBeInTheDocument()
    })
  })
})
