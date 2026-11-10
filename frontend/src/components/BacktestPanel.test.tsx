import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import BacktestPanel from './BacktestPanel'
import type { BacktestReport, BacktestVariant } from '../types'

vi.mock('../hooks/useBacktest', () => ({ useBacktest: vi.fn() }))
import { useBacktest } from '../hooks/useBacktest'
const mockUseBacktest = vi.mocked(useBacktest)

const variant = (key: string, label: string, group: BacktestVariant['group'], ret: number): BacktestVariant => ({
  key,
  label,
  group,
  final_equity: 10000 * (1 + ret / 100),
  return_pct: ret,
  max_drawdown_pct: -8,
  avg_invested_pct: 80,
  open_positions: 2,
  trades: 5,
  win_rate: 0.4,
  avg_return_pct: ret,
  median_return_pct: ret,
  avg_win_pct: 10,
  avg_loss_pct: -10,
  skipped: {},
  exits: {},
  accounts: {},
  curve: [
    { t: '2026-09-08', equity: 10000 },
    { t: '2026-11-06', equity: 10000 * (1 + ret / 100) },
  ],
})

const report: BacktestReport = {
  window: { start: '2026-09-05', end: '2026-11-06' },
  benchmark: { symbol: 'SPY', return_pct: -2.5 },
  signals: 2122,
  accounts_seen: 74,
  symbols_priced: 607,
  variants: [
    {
      ...variant('current', 'Current rules (6, 7, 8)', 'baseline', -12.6),
      trade_log: [
        {
          symbol: 'INTC',
          accounts: ['srxtrades'],
          entry_day: '2026-09-21',
          entry_price: 121.8,
          exit_day: '2026-10-30',
          exit_reason: 'rule6_stop',
          rules_hit: ['rule6_stop'],
          return_pct: -46,
          days_held: 39,
          cost: 1457,
        },
      ],
    },
    variant('time20', 'Sell after 20 trading days', 'exit', -1.9),
  ],
  accounts: [
    {
      account: 'chandlertrading',
      followed: true,
      d5: { signals: 12, hit_rate: 0.6, avg_return_pct: 1, avg_excess_pct: 0.8, beat_spy_rate: 0.5 },
      d20: null,
    },
  ],
  exit_study: {
    entries: 8147,
    symbols: 557,
    first_entry: '2024-08-28',
    last_entry: '2026-11-04',
    trend_filter: 'above_200d',
    rows: [
      {
        key: 'current',
        label: 'Current rules (6, 7, 8)',
        trades: 8147,
        avg_return_pct: 15.2,
        median_return_pct: -1.8,
        win_rate: 0.47,
        avg_days_held: 202,
        return_per_year_held_pct: 27.4,
        worst_pct: -93,
        p10_pct: -35.6,
        still_open: 2635,
        exits: {},
      },
    ],
  },
  assumptions: ['Buys fill at the next close.'],
  computed_at: '2026-11-09T17:00:00Z',
}

describe('BacktestPanel', () => {
  it('shows the variants against SPY, the exit study and the accounts', () => {
    const rerun = vi.fn()
    mockUseBacktest.mockReturnValue({ data: { status: 'ready', error: null, result: report }, failed: false, rerun })
    render(<BacktestPanel />)

    expect(screen.getByText(/2,122 bullish calls from 74 accounts/)).toBeInTheDocument()
    expect(screen.getAllByText('Current rules (6, 7, 8)').length).toBeGreaterThan(0)
    // -12.6% against SPY's -2.5% is 10.1 points behind.
    expect(screen.getByText('-10.1%')).toBeInTheDocument()
    expect(screen.getByText('+27.4%')).toBeInTheDocument()
    expect(screen.getByText('@chandlertrading')).toBeInTheDocument()
    expect(screen.getByText(/rule6 stop on 2026-10-30/)).toBeInTheDocument()

    fireEvent.click(screen.getByText('Run again'))
    expect(rerun).toHaveBeenCalled()
  })

  it('says it is running before the first result', () => {
    mockUseBacktest.mockReturnValue({ data: { status: 'running', error: null, result: null }, failed: false, rerun: vi.fn() })
    render(<BacktestPanel />)
    expect(screen.getByText(/takes a minute or two/)).toBeInTheDocument()
    expect(screen.getByText('Running…')).toBeDisabled()
  })
})
