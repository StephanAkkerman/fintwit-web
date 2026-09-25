import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { OverviewDashboard } from './OverviewDashboard'
import type { TrendSummary, TrendTicker } from '../types'

const N = 28

function ticker(t: string, mentions: number[], over: Partial<TrendTicker> = {}): TrendTicker {
  const total = mentions.reduce((a, b) => a + b, 0)
  const bull = mentions.map(m => Math.round(m * 0.6))
  const bear = mentions.map(m => Math.round(m * 0.2))
  return {
    ticker: t,
    asset_kind: 'EQUITY',
    mentions: total,
    previous_mentions: Math.round(total / 2),
    previous_rank: 2,
    unique_authors: 7,
    bull: bull.reduce((a, b) => a + b, 0),
    bear: bear.reduce((a, b) => a + b, 0),
    net_sentiment: 0.5,
    series: { mentions, bull, bear, price: mentions.map((_, i) => 100 + i) },
    ...over,
  }
}

function payload(over: Partial<TrendSummary> = {}): TrendSummary {
  const start = Date.UTC(2026, 8, 18)
  return {
    window: '7d',
    window_hours: 168,
    bucket_hours: 6,
    buckets: Array.from({ length: N }, (_, i) => new Date(start + i * 6 * 3600e3).toISOString()),
    data_since: '2026-01-01T00:00:00+00:00',
    totals: {
      tweets: { current: 420, previous: 300 },
      authors: { current: 90, previous: 80 },
      tickers: { current: 40, previous: 35 },
      net_sentiment: { current: 0.2, previous: 0.1 },
      series: {
        tweets: Array(N).fill(15), authors: Array(N).fill(5),
        bull: Array(N).fill(6), bear: Array(N).fill(3), tickers: Array(N).fill(8),
      },
    },
    kind_share: { current: { EQUITY: 300, CRYPTO: 120, FOREX: 0 }, previous: { EQUITY: 250, CRYPTO: 50, FOREX: 0 } },
    tickers: [
      ticker('NVDA', Array.from({ length: N }, (_, i) => 2 + i)),
      ticker('BTC', Array(N).fill(8), { asset_kind: 'CRYPTO' }),
      ticker('SMCI', Array.from({ length: N }, (_, i) => (i > 20 ? 6 : 0)), { previous_mentions: 0, previous_rank: null }),
    ],
    ...over,
  }
}

function stubFetch(body: unknown, ok = true) {
  const fetchMock = vi.fn().mockResolvedValue({ ok, json: async () => body })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => { vi.unstubAllGlobals() })

describe('OverviewDashboard', () => {
  it('renders the summary and every trend chart from one request', async () => {
    const fetchMock = stubFetch(payload())
    render(<OverviewDashboard />)

    expect(await screen.findByLabelText('Summary')).toBeInTheDocument()
    expect(screen.getByText(/broke out|appeared out of nowhere|led the/)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Mention growth against net sentiment per ticker' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Mention rank over time for the top tickers' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Net sentiment per ticker per time slot' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'NVDA price and mentions' })).toBeInTheDocument()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/overview/trend-summary?window=7d&asset_kind=all')
  })

  it('refetches when the timeframe changes', async () => {
    const fetchMock = stubFetch(payload())
    render(<OverviewDashboard />)
    await screen.findByLabelText('Summary')

    fireEvent.click(screen.getByRole('tab', { name: '30d' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(String(fetchMock.mock.calls[1][0])).toContain('window=30d')
    expect(screen.getByRole('tab', { name: '30d' })).toHaveAttribute('aria-selected', 'true')
  })

  it('opens a ticker when its name is clicked', async () => {
    stubFetch(payload())
    const onTickerClick = vi.fn()
    render(<OverviewDashboard onTickerClick={onTickerClick} />)
    await screen.findByLabelText('Summary')

    fireEvent.click(screen.getByRole('button', { name: /^NVDA: / }))
    expect(onTickerClick).toHaveBeenCalledWith('NVDA')
  })

  it('shows empty states when nothing was mentioned', async () => {
    stubFetch(payload({ tickers: [] }))
    render(<OverviewDashboard />)

    expect(await screen.findByText(/No ticker mentions in the past 7 days yet/)).toBeInTheDocument()
    expect(screen.getByText('Not enough activity to rank yet.')).toBeInTheDocument()
  })

  it('flags a window that reaches back further than the stored data', async () => {
    stubFetch(payload({ data_since: new Date(Date.now() - 2 * 86_400_000).toISOString() }))
    render(<OverviewDashboard />)

    expect(await screen.findByText(/Only 2\.0 days of tweets are stored/)).toBeInTheDocument()
  })

  it('reports a failed load instead of crashing on a non-object payload', async () => {
    stubFetch([])
    render(<OverviewDashboard />)

    expect(await screen.findByText(/Couldn't load the trend summary/)).toBeInTheDocument()
  })
})
