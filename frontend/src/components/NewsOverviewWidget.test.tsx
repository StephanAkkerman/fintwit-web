import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import NewsOverviewWidget, { briefingLine } from './NewsOverviewWidget'
import type { NewsOverviewResponse, NewsStory } from '../types'

vi.mock('../hooks/useNewsOverview', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/useNewsOverview')>()),
  useNewsOverview: vi.fn(),
}))

import { EMPTY_NEWS_OVERVIEW, useNewsOverview } from '../hooks/useNewsOverview'
const mockUseNewsOverview = vi.mocked(useNewsOverview)

function story(overrides: Partial<NewsStory>): NewsStory {
  return {
    title: 'Headline',
    url: `https://example.com/${overrides.title ?? 'headline'}`,
    source: 'Reuters',
    date: '2026-10-15T12:00:00Z',
    summary: '',
    symbols: ['SPY'],
    sources: ['Reuters'],
    article_count: 1,
    themes: [],
    sentiment_label: null,
    sentiment_score: null,
    related: [],
    score: 1,
    ...overrides,
  }
}

const LOADED: NewsOverviewResponse = {
  ...EMPTY_NEWS_OVERVIEW,
  top_stories: [
    story({
      title: 'Fed cuts rates',
      summary: 'The Federal Reserve lowered rates.',
      symbols: ['QQQ', 'SPY'],
      sources: ['CNBC', 'Reuters'],
      article_count: 2,
      themes: ['Fed & rates'],
      sentiment_label: 'BULLISH',
      sentiment_score: 0.7,
      related: [{ title: 'Fed lowers rates again', url: 'https://example.com/r', source: 'CNBC' }],
    }),
    story({ title: 'Oil slips' }),
  ],
  themes: [
    { name: 'Fed & rates', count: 2 },
    { name: 'Energy', count: 1 },
  ],
  articles: [
    { symbols: ['SPY'], title: 'Fed cuts rates', url: 'https://example.com/Fed cuts rates', date: '2026-10-15T12:00:00Z', source: 'Reuters' },
    { symbols: ['SPY'], title: 'Fed lowers rates again', url: 'https://example.com/r', date: '2026-10-15T12:00:00Z', source: 'CNBC' },
    { symbols: ['SPY'], title: 'Oil slips', url: 'https://example.com/Oil slips', date: '2026-10-15T11:00:00Z', source: 'Reuters' },
    { symbols: ['GC=F'], title: 'Gold steadies', url: 'https://example.com/gold', date: '2026-10-15T10:00:00Z', source: 'Bloomberg' },
  ],
  sentiment: { analyzed: 4, bullish: 3, neutral: 1, bearish: 0, mean_score: 0.4, label: 'BULLISH' },
  generated_at: '2026-10-15T12:30:00Z',
}

describe('NewsOverviewWidget', () => {
  beforeEach(() => {
    mockUseNewsOverview.mockReturnValue({ data: LOADED, loading: false, error: false })
  })

  it('summarises the news flow in one line', () => {
    expect(briefingLine(LOADED)).toBe(
      '4 headlines from 3 outlets, leaning bullish, mostly about Fed & rates, Energy.'
    )
  })

  it('ranks the top stories with their summary and coverage', () => {
    render(<NewsOverviewWidget />)
    const stories = within(screen.getByRole('list', { name: 'Top stories' }))
    expect(stories.getByText('Fed cuts rates')).toBeInTheDocument()
    expect(stories.getByText('The Federal Reserve lowered rates.')).toBeInTheDocument()
    expect(stories.getByText(/2 headlines · CNBC, Reuters/)).toBeInTheDocument()
    expect(stories.getByText('Fed lowers rates again')).toBeInTheDocument()
  })

  it('lists only the headlines that are not part of a top story', () => {
    render(<NewsOverviewWidget />)
    const more = within(screen.getByRole('list', { name: 'More headlines' }))
    expect(more.getAllByRole('link').map((link) => link.textContent)).toEqual(['Gold steadies'])
  })

  it('hands a clicked ticker to the caller', () => {
    const onTickerClick = vi.fn()
    render(<NewsOverviewWidget onTickerClick={onTickerClick} />)
    fireEvent.click(screen.getByRole('button', { name: 'QQQ' }))
    expect(onTickerClick).toHaveBeenCalledWith('QQQ')
  })

  it('says so when there is no news', () => {
    mockUseNewsOverview.mockReturnValue({ data: EMPTY_NEWS_OVERVIEW, loading: false, error: false })
    render(<NewsOverviewWidget />)
    expect(screen.getByText('No market news available right now.')).toBeInTheDocument()
  })
})
