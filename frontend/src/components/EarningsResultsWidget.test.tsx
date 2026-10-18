import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EarningsResultsWidget from './EarningsResultsWidget'
import type { EarningsResult, EarningsResults } from '../types'

vi.mock('../hooks/useEarningsResults', () => ({
  useEarningsResults: vi.fn(),
}))

import { useEarningsResults } from '../hooks/useEarningsResults'
const mockUseEarningsResults = vi.mocked(useEarningsResults)

function result(symbol: string, actual: number, forecast: number, surprise: number, outcome: EarningsResult['outcome']): EarningsResult {
  return {
    symbol,
    name: `${symbol} Inc.`,
    date: '2026-10-16',
    session: 'pre-market',
    session_emoji: '🌅',
    market_cap: 80_000_000_000,
    eps_forecast: forecast,
    num_estimates: 12,
    fiscal_quarter_ending: 'Sep/2026',
    last_year_eps: null,
    last_year_report_date: null,
    website: null,
    eps_actual: actual,
    surprise_pct: surprise,
    outcome,
  }
}

const DATA: EarningsResults = {
  start_date: '2026-10-12',
  end_date: '2026-10-16',
  results: [result('TRV', 9.18, 7.07, 29.84, 'beat'), result('BANF', 1.85, 1.93, -4.15, 'miss')],
  summary: { reported: 2, beat: 1, miss: 1, inline: 0 },
  source: 'nasdaq',
}

describe('EarningsResultsWidget', () => {
  beforeEach(() => {
    mockUseEarningsResults.mockReset()
  })

  it('lists reported EPS against the estimate with the surprise and outcome', () => {
    mockUseEarningsResults.mockReturnValue({ data: DATA, loading: false, error: false })
    render(<EarningsResultsWidget />)

    expect(screen.getByText('1 of 2 beat (50%)')).toBeInTheDocument()
    expect(screen.getByText('+29.8%')).toHaveClass('text-emerald-600')
    expect(screen.getByText('-4.2%')).toHaveClass('text-rose-600')
    expect(screen.getByText('Beat')).toBeInTheDocument()
    expect(screen.getByText('Miss')).toBeInTheDocument()
  })

  it('filters to misses', () => {
    mockUseEarningsResults.mockReturnValue({ data: DATA, loading: false, error: false })
    render(<EarningsResultsWidget />)

    fireEvent.click(screen.getByRole('button', { name: 'Misses' }))
    expect(screen.queryByText('TRV')).not.toBeInTheDocument()
    expect(screen.getByText('BANF')).toBeInTheDocument()
  })

  it('shows an empty state before anyone has reported', () => {
    mockUseEarningsResults.mockReturnValue({
      data: { ...DATA, results: [], summary: { reported: 0, beat: 0, miss: 0, inline: 0 } },
      loading: false,
      error: false,
    })
    render(<EarningsResultsWidget />)
    expect(screen.getByText('No companies have reported in this window yet.')).toBeInTheDocument()
  })

  it('shows an error state', () => {
    mockUseEarningsResults.mockReturnValue({ data: DATA, loading: false, error: true })
    render(<EarningsResultsWidget />)
    expect(screen.getByText('Could not load earnings results.')).toBeInTheDocument()
  })
})
