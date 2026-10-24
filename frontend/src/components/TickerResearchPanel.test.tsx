import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TickerResearchPanel from './TickerResearchPanel'
import type { AnalystActivity, DarkPool, OptionsFlow, TrendStage } from '../types'

const TREND: TrendStage = {
  symbol: 'NVDA',
  as_of: '2026-10-23',
  stage: {
    stage: 2,
    name: 'advancing',
    weeks_in_stage: 6,
    previous_stage: 1,
    ma30w: 186.4,
    price_vs_ma30w_percent: 7.8,
    ma30w_slope_5w_percent: 3.7,
  },
  vs_market: { mansfield: 9.4, mansfield_rising_4w: true, outperformance_13w_pp: 6, outperformance_26w_pp: 11 },
  benchmark: 'SPY',
  sector: {
    name: 'Technology',
    etf: 'XLK',
    stage: null,
    vs_market: { mansfield: 5.9, mansfield_rising_4w: false, outperformance_13w_pp: 2, outperformance_26w_pp: 7 },
    stock_vs_sector: { mansfield: -3.2, mansfield_rising_4w: false, outperformance_13w_pp: -1, outperformance_26w_pp: 3 },
  },
}

const ANALYSTS: AnalystActivity = {
  symbol: 'NVDA',
  rating_changes: {
    days: 90,
    upgrades: 2,
    downgrades: 1,
    initiations: 0,
    target_raises: 9,
    target_cuts: 1,
    recent_actions: [
      {
        date: '2026-10-17',
        firm: 'Morgan Stanley',
        action: 'upgrade',
        from_grade: 'Equal-Weight',
        to_grade: 'Overweight',
        price_target: 290,
        prior_price_target: 240,
        target_change_percent: 20.8,
      },
    ],
  },
  recommendations: { now: {}, three_months_ago: null, buy_percent: 93.5, buy_percent_change_3m: 5 },
  estimates: {
    direction: 'rising',
    periods: {
      '0y': { eps_estimate: 9.3, change_7d_percent: 0, change_30d_percent: 2.6, change_90d_percent: 6, up_30d: 9, down_30d: 1 },
    },
  },
}

const FLOW = {
  symbol: 'NVDA',
  bias: 'bullish',
  scored_trades: 6,
  large_trades: 9,
  scored_bullish_premium: 1_471_205,
  scored_bearish_premium: 513_743,
  call_premium: 2_774_663,
  put_premium: 1_503_851,
  top_scored: [
    {
      symbol: 'NVDA',
      direction: 'BULLISH',
      option_type: 'CALL',
      strike: 220,
      expiry: '2026-11-20',
      premium: 1_471_205,
      sweep: true,
      rationale: 'Flow confirms BUY',
      at: 'a',
    },
  ],
} as unknown as OptionsFlow

const DARK = { symbol: 'NVDA', prints: 50, notional: 11_331_467, lean: 'buyers' } as unknown as DarkPool

function respond(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

describe('TickerResearchPanel', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn((url: string) => {
      if (url.startsWith('/api/research/trend-stage')) return respond(TREND)
      if (url.startsWith('/api/research/analysts')) return respond(ANALYSTS)
      if (url.startsWith('/api/integrations/status')) return respond({ signa: true, reddit: true })
      if (url.startsWith('/api/signa/options-flow')) return respond(FLOW)
      if (url.startsWith('/api/signa/dark-pool')) return respond(DARK)
      return respond({}, 500)
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows the trend stage and analyst activity', async () => {
    render(<TickerResearchPanel ticker="nvda" />)

    expect(await screen.findByText('Stage 2 · Advancing')).toBeInTheDocument()
    expect(screen.getByText('6 weeks, after stage 1')).toBeInTheDocument()
    expect(screen.getByText('+7.8%')).toHaveClass('text-emerald-600')
    expect(screen.getByText('RS vs XLK')).toBeInTheDocument()
    expect(screen.getByText(/Technology \(XLK\)/)).toBeInTheDocument()

    expect(await screen.findByText(/rising \(\+2\.6% 30d\)/)).toBeInTheDocument()
    expect(screen.getByText('9 / 1')).toBeInTheDocument()
    expect(screen.getByText(/Morgan Stanley upgrade Overweight/)).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/research/trend-stage?symbol=NVDA', expect.anything())
  })

  it('loads options flow only on request', async () => {
    render(<TickerResearchPanel ticker="NVDA" />)
    await screen.findByText('Stage 2 · Advancing')
    expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith('/api/signa'))).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: 'Load flow and dark pool' }))

    expect(await screen.findByText('Bullish flow')).toBeInTheDocument()
    expect(screen.getAllByText('$1.5M').length).toBe(2) // bullish total and the trade
    expect(screen.getByText('buyers')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/signa/dark-pool?symbol=NVDA', expect.anything())
  })

  it('says when a symbol has no weekly history or analysts', async () => {
    fetchMock.mockImplementation((url: string) =>
      url.startsWith('/api/integrations/status') ? respond({ signa: false }) : respond({ detail: 'x' }, 404),
    )
    render(<TickerResearchPanel ticker="NEW" />)

    expect(await screen.findByText('Not enough weekly history.')).toBeInTheDocument()
    expect(screen.getByText('No analyst coverage.')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Needs a Signa key on the server.')).toBeInTheDocument())
  })

  it('treats a malformed payload as an error, not a crash', async () => {
    fetchMock.mockImplementation(() => respond([]))
    render(<TickerResearchPanel ticker="NVDA" />)

    expect(await screen.findByText('Could not load the trend stage.')).toBeInTheDocument()
    expect(screen.getByText('Could not load analyst data.')).toBeInTheDocument()
  })
})
