import { describe, expect, it } from 'vitest'
import type { TrendSummary, TrendTicker } from '../types'
import {
  SERIES_COLORS, assignSeriesColors, buildHeadline, fmtGrowth, fmtNet, growth, halves,
  priceChange, ranksOverTime, sentimentColor, type Segment,
} from '../utils/trendSummary'

const N = 8

function ticker(t: string, over: Partial<TrendTicker> & { mentionsSeries?: number[] } = {}): TrendTicker {
  const mentions = over.mentionsSeries ?? Array(N).fill(1)
  const total = mentions.reduce((a, b) => a + b, 0)
  return {
    ticker: t,
    asset_kind: 'EQUITY',
    mentions: total,
    previous_mentions: total,
    previous_rank: 1,
    unique_authors: 3,
    bull: 0,
    bear: 0,
    net_sentiment: null,
    series: { mentions, bull: Array(N).fill(0), bear: Array(N).fill(0), price: Array(N).fill(null) },
    ...over,
  }
}

function summary(tickers: TrendTicker[], over: Partial<TrendSummary> = {}): TrendSummary {
  return {
    window: '7d',
    window_hours: 168,
    bucket_hours: 6,
    buckets: Array.from({ length: N }, (_, i) => new Date(Date.UTC(2026, 8, 20 + i)).toISOString()),
    data_since: '2026-01-01T00:00:00+00:00',
    totals: {
      tweets: { current: 10, previous: 10 },
      authors: { current: 5, previous: 5 },
      tickers: { current: tickers.length, previous: tickers.length },
      net_sentiment: { current: 0.1, previous: 0 },
      series: { tweets: [], authors: [], bull: [], bear: [], tickers: [] },
    },
    kind_share: { current: { EQUITY: 10, CRYPTO: 0, FOREX: 0 }, previous: { EQUITY: 10, CRYPTO: 0, FOREX: 0 } },
    tickers,
    ...over,
  }
}

const text = (segs: Segment[]) =>
  segs.map(s => (typeof s === 'string' ? s : 'ticker' in s ? s.ticker : s.value)).join('')

describe('growth', () => {
  it('compares with the previous window and flags new tickers', () => {
    expect(growth({ mentions: 30, previous_mentions: 10 })).toBe(3)
    expect(growth({ mentions: 5, previous_mentions: 0 })).toBe(Infinity)
    expect(fmtGrowth(Infinity)).toBe('new')
    expect(fmtGrowth(2.345)).toBe('×2.3')
  })
})

describe('formatting', () => {
  it('signs net sentiment and leaves missing values as a dash', () => {
    expect(fmtNet(0.25)).toBe('+0.25')
    expect(fmtNet(-0.5)).toBe('−0.50')
    expect(fmtNet(null)).toBe('–')
  })
})

describe('sentimentColor', () => {
  it('is neutral grey at zero or unknown and saturates at the poles', () => {
    expect(sentimentColor(null)).toBe(sentimentColor(0))
    expect(sentimentColor(1)).toBe(sentimentColor(0.6))
    expect(sentimentColor(0.6)).not.toBe(sentimentColor(-0.6))
  })
})

describe('assignSeriesColors', () => {
  it('gives each ticker its own colour, independent of input order', () => {
    const names = ['NVDA', 'TSLA', 'BTC', 'ETH', 'SOL', 'AAPL', 'AMD', 'SPY']
    const a = assignSeriesColors(names)
    const b = assignSeriesColors([...names].reverse())
    expect(a).toEqual(b)
    expect(new Set(Object.values(a)).size).toBe(names.length)
    Object.values(a).forEach(c => expect(SERIES_COLORS).toContain(c))
  })
})

describe('ranksOverTime', () => {
  it('ranks on a trailing sum so the leader can change hands', () => {
    const a = ticker('AAA', { mentionsSeries: [5, 5, 5, 0, 0, 0, 0, 0] })
    const b = ticker('BBB', { mentionsSeries: [0, 0, 0, 1, 4, 4, 4, 4] })
    const ranks = ranksOverTime([a, b], 2)
    expect(ranks.get('AAA')![0]).toBe(1)
    expect(ranks.get('BBB')![0]).toBe(2)
    expect(ranks.get('AAA')![N - 1]).toBe(2)
    expect(ranks.get('BBB')![N - 1]).toBe(1)
  })
})

describe('halves and priceChange', () => {
  it('splits sentiment at the middle bucket', () => {
    const t = ticker('X', {})
    t.series.bull = [3, 3, 3, 3, 0, 0, 0, 0]
    t.series.bear = [0, 0, 0, 0, 2, 2, 2, 2]
    expect(halves(t)).toMatchObject({ first: 1, last: -1, firstN: 12, lastN: 8 })
  })

  it('needs two priced buckets', () => {
    const t = ticker('X')
    t.series.price = [null, 100, null, null, null, null, 110, null]
    expect(priceChange(t)?.change).toBeCloseTo(0.1)
    t.series.price = [null, 100, null, null, null, null, null, null]
    expect(priceChange(t)).toBeNull()
  })
})

describe('buildHeadline', () => {
  it('says so when there is nothing to summarise', () => {
    const h = buildHeadline(summary([]), 'all')
    expect(text(h.lead)).toMatch(/No ticker mentions/)
    expect(h.items).toEqual([])
  })

  it('leads with a breakout and a sentiment flip', () => {
    const steady = ticker('BTC', { mentionsSeries: Array(N).fill(10) })
    const breakout = ticker('SMCI', { mentionsSeries: [0, 0, 0, 0, 5, 10, 15, 20], previous_mentions: 5, previous_rank: 14 })
    const flipper = ticker('TSLA', { mentionsSeries: Array(N).fill(6) })
    flipper.series.bull = [3, 3, 3, 3, 0, 0, 0, 0]
    flipper.series.bear = [0, 0, 0, 0, 3, 3, 3, 3]
    const h = buildHeadline(summary([breakout, steady, flipper]), 'all')

    expect(text(h.lead)).toBe('SMCI broke out over the past 7 days with ×10 its previous chatter, while TSLA turned bearish.')
    expect(h.items[0].tone).toBe('bull')
    expect(text(h.items[1].segments)).toBe('TSLA sentiment went from +1.00 to −1.00 during the window.')
  })

  it('falls back to the leader when nothing is breaking out, and reports cooling and crypto share', () => {
    const leader = ticker('NVDA', { mentionsSeries: Array(N).fill(10) })
    const cooling = ticker('ETH', { mentionsSeries: Array(N).fill(2), previous_mentions: 40, asset_kind: 'CRYPTO' })
    const h = buildHeadline(summary([leader, cooling], {
      kind_share: { current: { EQUITY: 80, CRYPTO: 16, FOREX: 0 }, previous: { EQUITY: 80, CRYPTO: 40, FOREX: 0 } },
    }), 'all')

    expect(text(h.lead)).toBe('NVDA led the past 7 days with 80 mentions.')
    const lines = h.items.map(i => text(i.segments))
    expect(lines).toContain('Cooling off: ETH is down to 40% of its previous volume.')
    expect(lines).toContain("Crypto's share of all mentions went from 33% to 17%.")
  })

  it('lists new entrants to the top 10 and skips crypto share when filtered', () => {
    const leader = ticker('NVDA', { mentionsSeries: Array(N).fill(10) })
    const entrant = ticker('HOOD', { mentionsSeries: Array(N).fill(2), previous_rank: null, previous_mentions: 0 })
    const other = ticker('AAPL', { mentionsSeries: Array(N).fill(3) })
    const h = buildHeadline(summary([leader, other, entrant], {
      kind_share: { current: { EQUITY: 10, CRYPTO: 90, FOREX: 0 }, previous: { EQUITY: 90, CRYPTO: 10, FOREX: 0 } },
    }), 'EQUITY')
    const lines = h.items.map(i => text(i.segments))
    // HOOD is new, so it headlines as the breakout rather than as an entrant.
    expect(text(h.lead)).toMatch(/^HOOD appeared out of nowhere/)
    expect(lines.some(l => l.startsWith('Crypto'))).toBe(false)
  })
})
