import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CompanyNewsWidget from './CompanyNewsWidget'
import type { CompanyNewsArticle, CompanyNewsResponse } from '../types'

vi.mock('../hooks/useCompanyNews', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/useCompanyNews')>()),
  useCompanyNews: vi.fn(),
}))

import { EMPTY_NEWS_SENTIMENT, useCompanyNews } from '../hooks/useCompanyNews'
const mockUseCompanyNews = vi.mocked(useCompanyNews)

function article(overrides: Partial<CompanyNewsArticle>): CompanyNewsArticle {
  return {
    symbols: ['AAPL'],
    title: 'Headline',
    excerpt: null,
    url: `https://example.com/${overrides.title ?? 'headline'}`,
    date: '2026-09-01T12:00:00Z',
    source: 'Reuters',
    sentiment_label: null,
    sentiment_score: null,
    ...overrides,
  }
}

const SCORED: CompanyNewsResponse = {
  articles: [
    article({ title: 'Mild beat', date: '2026-09-03T12:00:00Z', sentiment_label: 'BULLISH', sentiment_score: 0.3 }),
    article({ title: 'Probe widens', date: '2026-09-02T12:00:00Z', sentiment_label: 'BEARISH', sentiment_score: -0.95 }),
    article({ title: 'Record demand', date: '2026-09-01T12:00:00Z', sentiment_label: 'BULLISH', sentiment_score: 0.8 }),
  ],
  sentiment: { analyzed: 3, bullish: 2, neutral: 0, bearish: 1, mean_score: 0.05, label: 'NEUTRAL' },
  source: 'yfinance',
}

function titles(): string[] {
  return within(screen.getByRole('list'))
    .getAllByRole('link')
    .map((link) => link.textContent ?? '')
}

describe('CompanyNewsWidget', () => {
  beforeEach(() => {
    mockUseCompanyNews.mockReturnValue({ data: SCORED, loading: false, error: false })
  })

  it('summarises which way the news leans', () => {
    render(<CompanyNewsWidget />)

    const overview = screen.getByTestId('news-sentiment-overview')
    expect(overview).toHaveTextContent('News on AAPL leans')
    expect(overview).toHaveTextContent('Neutral')
    expect(overview).toHaveTextContent('avg +0.05 across 3 headlines')
    expect(screen.getByRole('img', { name: '2 bullish, 0 neutral, 1 bearish' })).toBeInTheDocument()
    expect(screen.getByTestId('news-sentiment-timeline')).toBeInTheDocument()
  })

  it('filters headlines by sentiment', () => {
    render(<CompanyNewsWidget />)

    fireEvent.click(screen.getByRole('button', { name: /Bearish \(1\)/ }))

    expect(titles()).toEqual(['Probe widens'])
  })

  it('sorts by strongest signal', () => {
    render(<CompanyNewsWidget />)
    expect(titles()).toEqual(['Mild beat', 'Probe widens', 'Record demand'])

    fireEvent.change(screen.getByLabelText('Sort news'), { target: { value: 'strongest' } })

    expect(titles()).toEqual(['Probe widens', 'Record demand', 'Mild beat'])
  })

  it('falls back to a plain list when no sentiment model is loaded', () => {
    mockUseCompanyNews.mockReturnValue({
      data: { articles: [article({ title: 'Unscored' })], sentiment: EMPTY_NEWS_SENTIMENT, source: 'yfinance' },
      loading: false,
      error: false,
    })

    render(<CompanyNewsWidget />)

    expect(screen.getByTestId('news-sentiment-unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Filter by sentiment' })).not.toBeInTheDocument()
    expect(titles()).toEqual(['Unscored'])
  })
})
