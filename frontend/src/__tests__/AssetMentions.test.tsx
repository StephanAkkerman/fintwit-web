import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import AssetMentions from '../components/AssetMentions'
import type { MentionFrequency, TickerScopeStat } from '../types'

function stat(overrides: Partial<TickerScopeStat> = {}): TickerScopeStat {
  return {
    mentions: 12,
    prev_mentions: 9,
    signal: 'top',
    pct_change: 0.33,
    rank: 1,
    days_since_last: null,
    first_ever: false,
    stance: 'bullish',
    stance_bull: 10,
    stance_bear: 2,
    stance_total: 12,
    stance_flipped: false,
    notable: true,
    ...overrides,
  }
}

function makeLookup(freq: MentionFrequency | undefined) {
  return (_author: string, _ticker: string) => freq
}

describe('AssetMentions', () => {
  it('renders the author handle and an "all" line for a notable ticker', () => {
    const lookup = makeLookup({
      personal: stat(),
      global: stat({ signal: 'hot', mentions: 1200, stance: 'bearish', pct_change: null }),
    })
    render(<AssetMentions author="elonmusk" ticker="NVDA" lookup={lookup} />)

    expect(screen.getByText('@elonmusk')).toBeInTheDocument()
    expect(screen.getByText('all')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('1.2k')).toBeInTheDocument()
  })

  it('surfaces the % change inline as a trend label', () => {
    const lookup = makeLookup({
      personal: stat({ signal: 'rising', pct_change: 0.38 }),
      global: null,
    })
    render(<AssetMentions author="alice" ticker="SPY" lookup={lookup} />)
    expect(screen.getByText(/\+38%/)).toBeInTheDocument()
  })

  it('renders nothing when neither scope is notable', () => {
    const lookup = makeLookup({
      personal: stat({ signal: 'neutral', stance: null, stance_flipped: false, notable: false }),
      global: stat({ signal: 'neutral', stance: null, stance_flipped: false, notable: false }),
    })
    const { container } = render(<AssetMentions author="alice" ticker="AAPL" lookup={lookup} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when there is no stat for the ticker', () => {
    const lookup = makeLookup(undefined)
    const { container } = render(<AssetMentions author="alice" ticker="AAPL" lookup={lookup} />)
    expect(container).toBeEmptyDOMElement()
  })
})
