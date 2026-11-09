import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BreakoutScreenerWidget from './BreakoutScreenerWidget'
import type { Breakout, BreakoutHistory, BreakoutScreen } from '../types'

vi.mock('../hooks/useBreakouts', () => ({
  useBreakouts: vi.fn(),
}))

import { useBreakouts } from '../hooks/useBreakouts'
const mockUseBreakouts = vi.mocked(useBreakouts)

function row(symbol: string, overrides: Partial<Breakout> = {}): Breakout {
  return {
    symbol,
    name: `${symbol} Inc`,
    sector: 'Technology',
    industry: 'Semiconductors',
    close: 100,
    breakout_week: '2026-10-13',
    weeks_since_breakout: 4,
    base_weeks: 20,
    price_vs_ma30w_percent: 12.3,
    mansfield_rs: 18.5,
    rs_rising_4w: true,
    volume_ratio: 2.4,
    strong_volume: true,
    score: 70,
    signal: true,
    failed: [],
    status: 'breakout',
    flagged_at: '2026-11-03T12:00:00+00:00',
    flag_price: 95,
    last_close: 100,
    return_since_flag_pct: 5.26,
    ...overrides,
  }
}

const SCREEN: BreakoutScreen = {
  run: { id: 1, ran_at: '2026-11-09T12:00:00Z', as_of: '2026-11-09', universe: 240, evaluated: 231, breakouts: 1, watch: 1 },
  breakouts: [row('CRDO')],
  watch: [row('DOCU', { signal: false, failed: ['volume'], score: null, volume_ratio: 1.2 })],
  criteria: {
    fresh_weeks: 8,
    ma_weeks: 30,
    min_volume_ratio: 1.5,
    strong_volume_ratio: 2,
    min_mansfield: 0,
    max_extension_pct: 25,
    min_base_weeks: 6,
  },
}

const HISTORY: BreakoutHistory = {
  days: 180,
  summary: { flagged: 1, with_return: 1, avg_return_pct: 5.26, win_rate_pct: 100 },
  signals: [row('CRDO')],
}

describe('BreakoutScreenerWidget', () => {
  beforeEach(() => {
    mockUseBreakouts.mockReturnValue({ screen: SCREEN, history: HISTORY, loading: false, error: false })
  })

  it('lists breakouts and opens a ticker on click', () => {
    const onTickerClick = vi.fn()
    render(<BreakoutScreenerWidget onTickerClick={onTickerClick} />)

    expect(screen.getByText('Week of Nov 9 · 231 screened')).toBeInTheDocument()
    expect(screen.getByText('+18.5%')).toBeInTheDocument()
    expect(screen.getByText('2.4×')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'CRDO' }))
    expect(onTickerClick).toHaveBeenCalledWith('CRDO')
  })

  it('says what a near miss lacks', () => {
    render(<BreakoutScreenerWidget />)
    fireEvent.click(screen.getByRole('tab', { name: /Near misses/ }))

    expect(screen.getByText('DOCU')).toBeInTheDocument()
    expect(screen.getByText('light volume')).toBeInTheDocument()
  })

  it('shows the track record', () => {
    render(<BreakoutScreenerWidget />)
    fireEvent.click(screen.getByRole('tab', { name: /Track record/ }))

    expect(screen.getByText('$95.00')).toBeInTheDocument()
    expect(screen.getAllByText('+5.3%').length).toBeGreaterThan(0)
  })

  it('explains the wait before the first run', () => {
    mockUseBreakouts.mockReturnValue({
      screen: { run: null, breakouts: [], watch: [], criteria: null },
      history: { ...HISTORY, summary: { flagged: 0, with_return: 0, avg_return_pct: null, win_rate_pct: null }, signals: [] },
      loading: false,
      error: false,
    })
    render(<BreakoutScreenerWidget />)

    expect(screen.getByText(/first screen is still running/)).toBeInTheDocument()
  })
})
