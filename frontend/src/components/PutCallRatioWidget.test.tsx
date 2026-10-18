import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PutCallRatioWidget from './PutCallRatioWidget'
import type { PutCallRatios } from '../types'

vi.mock('../hooks/usePutCallRatio', () => ({
  usePutCallRatio: vi.fn(),
}))

import { usePutCallRatio } from '../hooks/usePutCallRatio'
const mockUsePutCallRatio = vi.mocked(usePutCallRatio)

const DATA: PutCallRatios = {
  date: '2026-10-16',
  ratios: [
    { key: 'total', value: 0.92, previous: 0.8, change: 0.12, average: 0.835 },
    { key: 'equity', value: 0.65, previous: 0.62, change: 0.03, average: 0.559 },
    { key: 'index', value: 1.05, previous: 0.99, change: 0.06, average: 0.972 },
    { key: 'vix', value: 0.32, previous: 0.35, change: -0.03, average: 0.374 },
  ],
  volume: { total: { call: 10_401_864, put: 9_619_756 } },
  sentiment: 'neutral',
  thresholds: { fear: 0.8, greed: 0.5 },
  history: [
    { date: '2026-10-15', total: 0.8, equity: 0.62, index: 0.99 },
    { date: '2026-10-16', total: 0.92, equity: 0.65, index: 1.05 },
  ],
  source: 'cboe',
}

describe('PutCallRatioWidget', () => {
  beforeEach(() => {
    mockUsePutCallRatio.mockReset()
  })

  it('shows the headline ratios with their change and average', () => {
    mockUsePutCallRatio.mockReturnValue({ data: DATA, loading: false, error: false })
    render(<PutCallRatioWidget />)

    expect(screen.getByText('0.92')).toBeInTheDocument()
    expect(screen.getByText('+0.12')).toBeInTheDocument()
    expect(screen.getByText('20-day avg 0.83')).toBeInTheDocument()
    expect(screen.getAllByText('Equity').length).toBeGreaterThan(0)
    expect(screen.getByText('Neutral')).toBeInTheDocument()
    // Secondary ratios sit in the compact row, falling change in green.
    expect(screen.getByText('-0.03')).toHaveClass('text-emerald-600')
    expect(screen.getByRole('img', { name: 'Put/call ratio history' })).toBeInTheDocument()
  })

  it('labels a high equity ratio as fearful', () => {
    mockUsePutCallRatio.mockReturnValue({
      data: { ...DATA, sentiment: 'fear' },
      loading: false,
      error: false,
    })
    render(<PutCallRatioWidget />)
    expect(screen.getByText('Fearful')).toBeInTheDocument()
  })

  it('shows an empty state when Cboe returned no session', () => {
    mockUsePutCallRatio.mockReturnValue({
      data: { ...DATA, ratios: [], history: [], sentiment: null },
      loading: false,
      error: false,
    })
    render(<PutCallRatioWidget />)
    expect(screen.getByText('No Cboe session data available right now.')).toBeInTheDocument()
  })

  it('shows an error state', () => {
    mockUsePutCallRatio.mockReturnValue({ data: null, loading: false, error: true })
    render(<PutCallRatioWidget />)
    expect(screen.getByText('Could not load put/call ratios.')).toBeInTheDocument()
  })
})
