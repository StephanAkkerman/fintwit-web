import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RedditSummaryPanel from '../components/RedditSummaryPanel'
import type { RedditTrendReport } from '../types'

function report(overrides: Partial<RedditTrendReport> = {}): RedditTrendReport {
  return {
    available: true,
    captured_at: new Date().toISOString(),
    subreddits: ['wallstreetbets', 'stocks'],
    tickers: [],
    window_hours: 24,
    posts_analyzed: 240,
    posts_in_window: 130,
    mood: 'bullish',
    sentiment_score: 0.21,
    sentiment_breakdown: { bullish: 60, neutral: 50, bearish: 20 },
    rising: ['NVDA', 'PLTR'],
    by_subreddit: [
      {
        subreddit: 'wallstreetbets',
        posts: 80,
        posts_with_tickers: 40,
        mood: 'bullish',
        sentiment_score: 0.3,
        top_tickers: { NVDA: 12, TSLA: 7, GME: 3, AMC: 1 },
      },
      { subreddit: 'stocks', posts: 50, posts_with_tickers: 10, mood: 'neutral', sentiment_score: 0.05 },
    ],
    ...overrides,
  }
}

describe('RedditSummaryPanel', () => {
  it('summarises mood, volume and the per-subreddit breakdown', () => {
    render(<RedditSummaryPanel data={report()} />)

    expect(screen.getByText('Reddit Summary')).toBeInTheDocument()
    expect(screen.getByText('bullish')).toBeInTheDocument()
    expect(screen.getByText('130')).toBeInTheDocument()
    expect(screen.getByText('240')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Bullish 46%, neutral 38%, bearish 15%/ })).toBeInTheDocument()
    expect(screen.getByText('NVDA, PLTR')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'r/wallstreetbets' })).toBeInTheDocument()
    // share of posts naming a ticker, and only the top three tickers
    expect(screen.getByText('50%')).toBeInTheDocument()
    expect(screen.getByText('NVDA 12 · TSLA 7 · GME 3')).toBeInTheDocument()
  })

  it('renders nothing before the first run', () => {
    const { container } = render(<RedditSummaryPanel data={report({ captured_at: null })} />)
    expect(container).toBeEmptyDOMElement()
  })
})
