import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdvisorPanel from './AdvisorPanel'
import type { AdvisorCall } from '../types'

vi.mock('../hooks/useAdvisor', () => ({
  useAdvisor: vi.fn(),
}))

import { useAdvisor } from '../hooks/useAdvisor'
const mockUseAdvisor = vi.mocked(useAdvisor)

const call = (overrides: Partial<AdvisorCall>): AdvisorCall => ({
  id: 1,
  symbol: 'NVDA',
  action: 'buy',
  conviction: 'high',
  price_at_call: 100,
  asset_kind: 'EQUITY',
  reasoning: 'Sentiment turned bullish ahead of earnings',
  rule: 'Max 20% per position',
  called_at: '2026-10-01T14:00:00Z',
  results: {},
  ...overrides,
})

function mockState(overrides: Partial<ReturnType<typeof useAdvisor>> = {}) {
  const saveStrategy = vi.fn().mockResolvedValue({})
  mockUseAdvisor.mockReturnValue({
    strategy: {
      rules: 'No penny stocks',
      watchlist: ['NVDA', 'AMD'],
      followed_traders: ['shardib2'],
      available_cash: 2500,
      cash_currency: 'EUR',
      updated_at: null,
    },
    calls: [],
    runs: [],
    scorecard: { total_calls: 0, horizons: {} },
    paper: [],
    loading: false,
    error: false,
    saveStrategy,
    reload: vi.fn(),
    ...overrides,
  })
  return saveStrategy
}

beforeEach(() => vi.clearAllMocks())

describe('AdvisorPanel', () => {
  it('shows the empty journal and the saved strategy', () => {
    mockState()
    render(<AdvisorPanel />)
    expect(screen.getByText(/No calls yet/i)).toBeTruthy()
    expect((screen.getByLabelText('Strategy rules') as HTMLTextAreaElement).value).toBe('No penny stocks')
    expect((screen.getByLabelText('Watchlist') as HTMLInputElement).value).toBe('NVDA, AMD')
    expect(screen.getAllByText(/Nothing graded yet/i)).toHaveLength(2)
  })

  it('shows followed returns, so a sell before a drop reads as a gain', () => {
    mockState({
      calls: [
        call({
          id: 2,
          symbol: 'TSLA',
          action: 'sell',
          results: {
            '7': { horizon_days: 7, price_at_horizon: 90, return_pct: -10, correct: true, excluded: false, evaluated_at: null },
          },
        }),
        call({ id: 1, action: 'watch', reasoning: 'Keep an eye on it', rule: null }),
      ],
      scorecard: {
        total_calls: 2,
        horizons: { '7': { graded: 1, hit_rate: 1, avg_return_pct: 10, by_action: {} } },
      },
    })
    render(<AdvisorPanel />)
    expect(screen.getByText('+10.0%')).toBeTruthy()
    expect(screen.getByText('TSLA')).toBeTruthy()
    expect(screen.getByText('Keep an eye on it')).toBeTruthy()
    expect(screen.getByText('100%')).toBeTruthy()
  })

  it('saves the strategy with the watchlist split into symbols', async () => {
    const save = mockState()
    render(<AdvisorPanel />)
    fireEvent.change(screen.getByLabelText('Watchlist'), { target: { value: 'pltr, amd  msft' } })
    fireEvent.click(screen.getByText('Save strategy'))
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith({
        rules: 'No penny stocks',
        watchlist: ['pltr', 'amd', 'msft'],
        followed_traders: ['shardib2'],
        available_cash: 2500,
        cash_currency: 'EUR',
      }),
    )
    expect(await screen.findByText('Saved')).toBeTruthy()
  })

  it('lists recent checks', () => {
    mockState({
      runs: [
        {
          id: 1,
          ran_at: '2026-10-12T12:00:00Z',
          tweet_cursor: '1977000000000000000',
          session: 'Pre-market',
          posts_read: 214,
          summary: 'BUY GTLB after @ShardiB2; fundamentals and technicals both pass.',
        },
      ],
    })
    render(<AdvisorPanel />)
    expect(screen.getByText('Pre-market')).toBeTruthy()
    expect(screen.getByText('214 posts')).toBeTruthy()
    expect(screen.getByText(/BUY GTLB after @ShardiB2/)).toBeTruthy()
  })

  it('saves followed traders without the @', async () => {
    const save = mockState()
    render(<AdvisorPanel />)
    const followed = screen.getByLabelText('Traders you follow') as HTMLInputElement
    expect(followed.value).toBe('@shardib2')
    fireEvent.change(followed, { target: { value: '@ShardiB2, someone' } })
    fireEvent.click(screen.getByText('Save strategy'))
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith(expect.objectContaining({ followed_traders: ['ShardiB2', 'someone'] })),
    )
  })

  it('clears the cash, and refuses a negative amount', async () => {
    const save = mockState()
    render(<AdvisorPanel />)
    const cash = screen.getByLabelText('Cash available to invest')
    fireEvent.change(cash, { target: { value: '-5' } })
    // The browser's own min=0 validation blocks the submit.
    fireEvent.click(screen.getByText('Save strategy'))
    expect(save).not.toHaveBeenCalled()

    fireEvent.change(cash, { target: { value: '' } })
    fireEvent.click(screen.getByText('Save strategy'))
    await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({ available_cash: null })))
  })

  it('ranks the paper strategies by return and lists their trades', () => {
    const portfolio = {
      entry: 'Three insiders bought',
      exit: 'Below the 50-day',
      max_hold_days: 30,
      open: 0,
      closed: 0,
      win_rate: null,
      avg_return_pct: null,
      positions: [],
      scores: {},
    }
    mockState({
      paper: [
        { ...portfolio, strategy: 'call_flow', label: 'Big call buying' },
        {
          ...portfolio,
          strategy: 'insider_cluster',
          label: 'Insider cluster buys',
          open: 1,
          closed: 1,
          win_rate: 1,
          avg_return_pct: 6.5,
          scores: { '7': { graded: 2, hit_rate: 0.5, avg_return_pct: 3 } },
          positions: [
            {
              symbol: 'KMI',
              entry_call_id: 4,
              entry_price: 26,
              entered_at: '2026-10-20T14:00:00Z',
              exit_price: null,
              exited_at: null,
              exit_reason: null,
              status: 'open',
              price_now: 27.3,
              return_pct: 5,
              days_held: 3,
            },
          ],
        },
      ],
    })
    render(<AdvisorPanel />)
    const rows = screen.getAllByRole('row').map((row) => row.textContent)
    const insider = rows.findIndex((text) => text?.startsWith('Insider cluster buys'))
    const flow = rows.findIndex((text) => text?.startsWith('Big call buying'))
    expect(insider).toBeGreaterThan(0)
    expect(insider).toBeLessThan(flow)
    expect(rows[insider]).toContain('+6.5%')
    expect(rows[insider]).toContain('50% of 2')
    expect(screen.getByText('26.00 → 27.30')).toBeTruthy()
    expect(screen.getByText('open, 3d')).toBeTruthy()
  })

  it('hides the paper strategies when there are none', () => {
    mockState()
    render(<AdvisorPanel />)
    expect(screen.queryByText('Paper strategies')).toBeNull()
  })

  it('shows an error state', () => {
    mockState({ error: true })
    render(<AdvisorPanel />)
    expect(screen.getByText(/Failed to load the market check data/i)).toBeTruthy()
  })
})
