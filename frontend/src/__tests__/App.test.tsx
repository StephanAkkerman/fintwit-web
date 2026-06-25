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
    if (url.includes('/api/binance/gainers-losers')) {
      return Promise.resolve({ ok: true, json: async () => ({ gainers: [], losers: [] }) } as Response)
    }
    if (url.includes('/api/treemap')) {
      return Promise.resolve({ ok: true, json: async () => ({ data: [] }) } as Response)
    }
    if (url.includes('/api/stocktwits')) {
      return Promise.resolve({ ok: true, json: async () => [] } as Response)
    }
    if (url.includes('/api/stocks/extended-hours')) {
      return Promise.resolve(
        {
          ok: true,
          json: async () => ({
            session: 'regular',
            window_start: '2026-06-25T04:00:00-04:00',
            window_end: '2026-06-25T09:30:00-04:00',
            futures: [],
            etfs: [],
            tweet_stats: {
              total_mentions: 0,
              top_tickers: [],
              sentiment_distribution: { BULL: 0, BEAR: 0, NEUTRAL: 0 },
            },
          }),
        } as Response
      )
    }
    if (url.includes('/api/stocks/market-hours')) {
      return Promise.resolve({ ok: true, json: async () => [] } as Response)
    }
    if (url.includes('/api/stock-halts')) {
      return Promise.resolve({ ok: true, json: async () => [] } as Response)
    }
    if (url.includes('/api/events/economic')) {
      return Promise.resolve({ ok: true, json: async () => [] } as Response)
    }
    if (url.includes('/api/options/overview')) {
      return Promise.resolve(
        {
          ok: true,
          json: async () => ({
            symbols: [],
            totals: { call_volume: 0, put_volume: 0, total_volume: 0, put_call_ratio: null },
            bullish: [],
            bearish: [],
            most_active_contracts: [],
            source: 'nasdaq',
          }),
        } as Response
      )
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
    if (url.includes('/api/ibkr/status')) {
      return Promise.resolve(
        {
          ok: true,
          json: async () => ({ configured: false, connected: false, last_sync: null, last_error: null }),
        } as Response
      )
    }
    if (url.includes('/api/ibkr/positions')) {
      return Promise.resolve({ ok: true, json: async () => [] } as Response)
    }
    if (url.includes('/api/ibkr/trades')) {
      return Promise.resolve({ ok: true, json: async () => [] } as Response)
    }
    if (url.includes('/api/ibkr/account')) {
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
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
  })

  it('does not render legacy category filter widget', async () => {
    render(<App />)

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /x stream/i })).toBeInTheDocument()
    )

    expect(screen.queryByText('Filters')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Timeline filter Crypto' })).not.toBeInTheDocument()
  })

  it('shows crypto section widgets when navigating to /crypto', async () => {
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'Open /crypto' }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /trending crypto/i })).toBeInTheDocument()
    )
    expect(screen.getByRole('heading', { name: /binance movers/i })).toBeInTheDocument()
    expect(screen.getByText(/top coins by market cap/i)).toBeInTheDocument()
    expect(window.location.pathname).toBe('/crypto')
  })

  it('shows stock section widgets when navigating to /stocks', async () => {
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'Open /stocks' }))

    await waitFor(() =>
      expect(screen.getByText(/stocktwits signals/i)).toBeInTheDocument()
    )
    expect(screen.getByRole('heading', { name: /nasdaq trading halts/i })).toBeInTheDocument()
    expect(screen.getByText(/major exchange sessions/i)).toBeInTheDocument()
    expect(screen.getByText(/spy heatmap/i)).toBeInTheDocument()
    expect(window.location.pathname).toBe('/stocks')
  })

  it('shows forex section widget when navigating to /forex', async () => {
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'Open /forex' }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /economic events/i })).toBeInTheDocument()
    )
    expect(window.location.pathname).toBe('/forex')
  })

  it('shows options section widget when navigating to /options', async () => {
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'Open /options' }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /options overview/i })).toBeInTheDocument()
    )
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some((call) => String(call[0]).includes('/api/posts?limit=200&since_hours=24&options_only=true'))
      ).toBe(true)
    })
    expect(window.location.pathname).toBe('/options')
  })

  it('switches lookback window and refreshes performance stats', async () => {
    const oneTweet: Tweet[] = [
      {
        id: 1,
        text: '$BTC first pass',
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
        assets: [{ symbol: 'BTC', kind: 'CRYPTO' }],
      },
    ]

    const threeTweets: Tweet[] = [
      oneTweet[0],
      {
        id: 2,
        text: '$ETH second pass',
        user_name: 'Crypto User',
        user_screen_name: 'crypto_user',
        user_img: 'https://example.com/c.jpg',
        url: 'https://x.com/crypto_user/status/2',
        created_at: '',
        media: [],
        tickers: ['ETH'],
        hashtags: [],
        title: '',
        media_types: [],
        replies: 0,
        likes: 0,
        views: 0,
        retweets: 0,
        assets: [{ symbol: 'ETH', kind: 'CRYPTO' }],
      },
      {
        id: 3,
        text: '$SOL third pass',
        user_name: 'Crypto User',
        user_screen_name: 'crypto_user',
        user_img: 'https://example.com/c.jpg',
        url: 'https://x.com/crypto_user/status/3',
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
        assets: [{ symbol: 'SOL', kind: 'CRYPTO' }],
      },
    ]

    fetchMock.mockImplementation((input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('/api/posts?limit=200&since_hours=24')) {
        return Promise.resolve({ ok: true, json: async () => oneTweet } as Response)
      }
      if (url.includes('/api/posts?limit=200&since_hours=168')) {
        return Promise.resolve({ ok: true, json: async () => threeTweets } as Response)
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
      if (url.includes('/api/binance/gainers-losers')) {
        return Promise.resolve({ ok: true, json: async () => ({ gainers: [], losers: [] }) } as Response)
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
      if (url.includes('/api/stock-halts')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/events/economic')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/options/overview')) {
        return Promise.resolve(
          {
            ok: true,
            json: async () => ({
              symbols: [],
              totals: { call_volume: 0, put_volume: 0, total_volume: 0, put_call_ratio: null },
              bullish: [],
              bearish: [],
              most_active_contracts: [],
              source: 'nasdaq',
            }),
          } as Response
        )
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
      if (url.includes('/api/ibkr/status')) {
        return Promise.resolve(
          {
            ok: true,
            json: async () => ({ configured: false, connected: false, last_sync: null, last_error: null }),
          } as Response
        )
      }
      if (url.includes('/api/ibkr/positions')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/trades')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/account')) {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
      }

      return Promise.resolve({ ok: true, json: async () => [] } as Response)
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText(/current window: last 24h/i)).toBeInTheDocument()
      expect(screen.getByText('Fetched tweets: 1')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Lookback 7d' }))

    await waitFor(() => {
      expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('/api/posts?limit=200&since_hours=168'))).toBe(true)
      expect(screen.getByText(/current window: last 168h/i)).toBeInTheDocument()
      expect(screen.getByText('Fetched tweets: 3')).toBeInTheDocument()
    })
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
      if (url.includes('/api/ibkr/status')) {
        return Promise.resolve(
          {
            ok: true,
            json: async () => ({ configured: false, connected: false, last_sync: null, last_error: null }),
          } as Response
        )
      }
      if (url.includes('/api/ibkr/positions')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/trades')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/account')) {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
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
      if (url.includes('/api/ibkr/status')) {
        return Promise.resolve(
          {
            ok: true,
            json: async () => ({ configured: false, connected: false, last_sync: null, last_error: null }),
          } as Response
        )
      }
      if (url.includes('/api/ibkr/positions')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/trades')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/account')) {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('Stock User')).toBeInTheDocument()
      expect(screen.getByText('Crypto User')).toBeInTheDocument()
    })

    fireEvent.click(screen.getAllByRole('button', { name: 'Filter by $AAPL' })[0])

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
      if (url.includes('/api/ibkr/status')) {
        return Promise.resolve(
          {
            ok: true,
            json: async () => ({ configured: false, connected: false, last_sync: null, last_error: null }),
          } as Response
        )
      }
      if (url.includes('/api/ibkr/positions')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/trades')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/account')) {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('Sol User')).toBeInTheDocument()
      expect(screen.getByText('Apple User')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Ticker symbol'), { target: { value: '$sol' } })
    fireEvent.submit(screen.getByLabelText('Ticker symbol').closest('form') as HTMLFormElement)

    await waitFor(() => {
      expect(screen.getByText('Sol User')).toBeInTheDocument()
      expect(screen.queryByText('Apple User')).not.toBeInTheDocument()
      expect(screen.getAllByRole('button', { name: 'Filter by $SOL' }).length).toBeGreaterThan(0)
    })
  })

  it('filters tweets by typed user input', async () => {
    const posts: Tweet[] = [
      {
        id: 1,
        text: '$SPY update',
        user_name: 'Stock User',
        user_screen_name: 'stock_user',
        user_img: 'https://example.com/s.jpg',
        url: 'https://x.com/stock_user/status/1',
        created_at: '',
        media: [],
        tickers: ['SPY'],
        hashtags: [],
        title: '',
        media_types: [],
        replies: 0,
        likes: 0,
        views: 0,
        retweets: 0,
        assets: [{ symbol: 'SPY', kind: 'EQUITY' }],
      },
      {
        id: 2,
        text: '$QQQ update',
        user_name: 'Macro User',
        user_screen_name: 'macro_user',
        user_img: 'https://example.com/m.jpg',
        url: 'https://x.com/macro_user/status/2',
        created_at: '',
        media: [],
        tickers: ['QQQ'],
        hashtags: [],
        title: '',
        media_types: [],
        replies: 0,
        likes: 0,
        views: 0,
        retweets: 0,
        assets: [{ symbol: 'QQQ', kind: 'EQUITY' }],
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
      if (url.includes('/api/ibkr/status')) {
        return Promise.resolve(
          {
            ok: true,
            json: async () => ({ configured: false, connected: false, last_sync: null, last_error: null }),
          } as Response
        )
      }
      if (url.includes('/api/ibkr/positions')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/trades')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/account')) {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('Stock User')).toBeInTheDocument()
      expect(screen.getByText('Macro User')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('User name'), { target: { value: '@stock_user' } })
    fireEvent.submit(screen.getByLabelText('User name').closest('form') as HTMLFormElement)

    await waitFor(() => {
      expect(screen.getByText('Stock User')).toBeInTheDocument()
      expect(screen.queryByText('Macro User')).not.toBeInTheDocument()
      expect(screen.getByLabelText('User name')).toHaveValue('stock_user')
    })
  })

  it('filters tweets to subscriber-only posts when enabled', async () => {
    const posts: Tweet[] = [
      {
        id: 1,
        text: 'Regular timeline post',
        user_name: 'Public User',
        user_screen_name: 'public_user',
        user_img: 'https://example.com/public.jpg',
        url: 'https://x.com/public_user/status/1',
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
      },
      {
        id: 2,
        text: 'Subscriber-only alpha',
        user_name: 'Paid User',
        user_screen_name: 'paid_user',
        user_img: 'https://example.com/paid.jpg',
        url: 'https://x.com/paid_user/status/2',
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
        is_subscriber_only: true,
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
      if (url.includes('/api/binance/gainers-losers')) {
        return Promise.resolve({ ok: true, json: async () => ({ gainers: [], losers: [] }) } as Response)
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
      if (url.includes('/api/stock-halts')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/events/economic')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/options/overview')) {
        return Promise.resolve(
          {
            ok: true,
            json: async () => ({
              symbols: [],
              totals: { call_volume: 0, put_volume: 0, total_volume: 0, put_call_ratio: null },
              bullish: [],
              bearish: [],
              most_active_contracts: [],
              source: 'nasdaq',
            }),
          } as Response
        )
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
      if (url.includes('/api/ibkr/status')) {
        return Promise.resolve(
          {
            ok: true,
            json: async () => ({ configured: false, connected: false, last_sync: null, last_error: null }),
          } as Response
        )
      }
      if (url.includes('/api/ibkr/positions')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/trades')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/account')) {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
      }

      return Promise.resolve({ ok: true, json: async () => [] } as Response)
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('Regular timeline post')).toBeInTheDocument()
      expect(screen.getByText('Subscriber-only alpha')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Subscriber-only tweets' }))

    await waitFor(() => {
      expect(screen.getByText('Subscriber-only alpha')).toBeInTheDocument()
      expect(screen.queryByText('Regular timeline post')).not.toBeInTheDocument()
    })
  })

  it('updates ticker mention pulse when user filter changes', async () => {
    const posts: Tweet[] = [
      {
        id: 1,
        text: '$AAPL update from equity side',
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
        assets: [{ symbol: 'AAPL', kind: 'EQUITY' }],
      },
      {
        id: 2,
        text: '$BTC momentum',
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
        assets: [{ symbol: 'BTC', kind: 'CRYPTO' }],
      },
      {
        id: 3,
        text: '$ETH setup',
        user_name: 'Crypto User',
        user_screen_name: 'crypto_user',
        user_img: 'https://example.com/c.jpg',
        url: 'https://x.com/crypto_user/status/3',
        created_at: '',
        media: [],
        tickers: ['ETH'],
        hashtags: [],
        title: '',
        media_types: [],
        replies: 0,
        likes: 0,
        views: 0,
        retweets: 0,
        assets: [{ symbol: 'ETH', kind: 'CRYPTO' }],
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
      if (url.includes('/api/ibkr/status')) {
        return Promise.resolve(
          {
            ok: true,
            json: async () => ({ configured: false, connected: false, last_sync: null, last_error: null }),
          } as Response
        )
      }
      if (url.includes('/api/ibkr/positions')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/trades')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/account')) {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /ticker mention pulse/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Filter by analytics ticker $AAPL' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Filter by analytics ticker $BTC' })).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('User name'), { target: { value: '@crypto_user' } })
    fireEvent.submit(screen.getByLabelText('User name').closest('form') as HTMLFormElement)

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: 'Filter by analytics ticker $AAPL' })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Filter by analytics ticker $BTC' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Filter by analytics ticker $ETH' })).toBeInTheDocument()
      expect(screen.getByText(/focused on @crypto_user/i)).toBeInTheDocument()
    })
  })

  it('filters tweets by clicking user name or profile image', async () => {
    const posts: Tweet[] = [
      {
        id: 1,
        text: '$AAPL setup',
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
        assets: [{ symbol: 'AAPL', kind: 'EQUITY' }],
      },
      {
        id: 2,
        text: '$MSFT setup',
        user_name: 'Tech User',
        user_screen_name: 'tech_user',
        user_img: 'https://example.com/t.jpg',
        url: 'https://x.com/tech_user/status/2',
        created_at: '',
        media: [],
        tickers: ['MSFT'],
        hashtags: [],
        title: '',
        media_types: [],
        replies: 0,
        likes: 0,
        views: 0,
        retweets: 0,
        assets: [{ symbol: 'MSFT', kind: 'EQUITY' }],
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
      if (url.includes('/api/ibkr/status')) {
        return Promise.resolve(
          {
            ok: true,
            json: async () => ({ configured: false, connected: false, last_sync: null, last_error: null }),
          } as Response
        )
      }
      if (url.includes('/api/ibkr/positions')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/trades')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/account')) {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
    })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('Stock User')).toBeInTheDocument()
      expect(screen.getByText('Tech User')).toBeInTheDocument()
    })

    fireEvent.click(screen.getAllByRole('button', { name: 'Filter by user @stock_user' })[0])

    await waitFor(() => {
      expect(screen.getByText('Stock User')).toBeInTheDocument()
      expect(screen.queryByText('Tech User')).not.toBeInTheDocument()
      expect(screen.getByLabelText('User name')).toHaveValue('stock_user')
    })
  })

  it('shows only options-classified tweets on the options route', async () => {
    const posts: Tweet[] = [
      {
        id: 1,
        text: '$TSLA AUG 390c up about 15%',
        user_name: 'Options User',
        user_screen_name: 'options_user',
        user_img: 'https://example.com/options.jpg',
        url: 'https://x.com/options/status/1',
        created_at: '',
        is_options_tweet: true,
        media: [],
        tickers: ['TSLA'],
        hashtags: [],
        title: '',
        media_types: [],
        replies: 0,
        likes: 0,
        views: 0,
        retweets: 0,
        assets: [{ symbol: 'TSLA', kind: 'EQUITY' }],
      },
      {
        id: 2,
        text: '$AAPL long update',
        user_name: 'Spot User',
        user_screen_name: 'spot_user',
        user_img: 'https://example.com/spot.jpg',
        url: 'https://x.com/spot/status/2',
        created_at: '',
        is_options_tweet: false,
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
    ]

    fetchMock.mockImplementation((input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('/api/posts')) {
        return Promise.resolve({ ok: true, json: async () => posts } as Response)
      }
      if (url.includes('/api/options/overview')) {
        return Promise.resolve(
          {
            ok: true,
            json: async () => ({
              symbols: [],
              totals: { call_volume: 0, put_volume: 0, total_volume: 0, put_call_ratio: null },
              bullish: [],
              bearish: [],
              most_active_contracts: [],
              source: 'nasdaq',
            }),
          } as Response
        )
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
      if (url.includes('/api/ibkr/status')) {
        return Promise.resolve(
          {
            ok: true,
            json: async () => ({ configured: false, connected: false, last_sync: null, last_error: null }),
          } as Response
        )
      }
      if (url.includes('/api/ibkr/positions')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/trades')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/account')) {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
    })

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Open /options' }))

    await waitFor(() => {
      expect(screen.getByText('Options User')).toBeInTheDocument()
      expect(screen.queryByText('Spot User')).not.toBeInTheDocument()
    })
  })

  it('filters tweets to forex/macro signals on the forex route', async () => {
    const posts: Tweet[] = [
      {
        id: 1,
        text: '$EURUSD pair outlook',
        user_name: 'Forex User',
        user_screen_name: 'forex_user',
        user_img: 'https://example.com/f.jpg',
        url: 'https://x.com/f/1',
        created_at: '',
        media: [],
        tickers: ['EURUSD'],
        hashtags: [],
        title: '',
        media_types: [],
        replies: 0,
        likes: 0,
        views: 0,
        retweets: 0,
        assets: [{ symbol: 'EURUSD', kind: 'FOREX' }],
      },
      {
        id: 2,
        text: '$AAPL breakout',
        user_name: 'Stock User',
        user_screen_name: 'stock_user',
        user_img: 'https://example.com/s.jpg',
        url: 'https://x.com/s/2',
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
        text: '$BTC moon',
        user_name: 'Crypto User',
        user_screen_name: 'crypto_user',
        user_img: 'https://example.com/c.jpg',
        url: 'https://x.com/c/3',
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
        assets: [{ symbol: 'BTC', kind: 'CRYPTO' }],
      },
    ]

    fetchMock.mockImplementation((input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('/api/posts')) {
        return Promise.resolve({ ok: true, json: async () => posts } as Response)
      }
      if (url.includes('/api/ibkr/positions')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/trades')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/account')) {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
      }
      if (url.includes('/api/ibkr/status')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ configured: false, connected: false, last_sync: null, last_error: null }),
        } as Response)
      }
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
    })

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Open /forex' }))

    await waitFor(() => {
      expect(screen.getByText('Forex User')).toBeInTheDocument()
      expect(screen.queryByText('Stock User')).not.toBeInTheDocument()
      expect(screen.queryByText('Crypto User')).not.toBeInTheDocument()
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
      if (url.includes('/api/ibkr/status')) {
        return Promise.resolve(
          {
            ok: true,
            json: async () => ({ configured: false, connected: false, last_sync: null, last_error: null }),
          } as Response
        )
      }
      if (url.includes('/api/ibkr/positions')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/trades')) {
        return Promise.resolve({ ok: true, json: async () => [] } as Response)
      }
      if (url.includes('/api/ibkr/account')) {
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response)
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
