import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SignaBestTradesWidget from '../components/SignaBestTradesWidget'
import type { SignaBestTrade } from '../types'

const SIGNALS: SignaBestTrade[] = [
  {
    source: 'signa',
    symbol: 'LOWER',
    direction: 'BULLISH',
    grade: 'B',
    alert_tier: 1,
    composite_score: 80,
    confidence: 0.5,
    model_count: 2,
    regime: 'TRANSITIONAL',
    categories: [],
    reason: 'A weaker setup',
    key_drivers: ['driver one'],
    model_ids: ['macd-signal'],
    generated_at: new Date(Date.now() - 17 * 60_000).toISOString(),
    website: 'https://app.getsigna.ai/dashboard/best-trades',
  },
  {
    source: 'signa',
    symbol: 'TOPPICK',
    direction: 'BEARISH',
    grade: 'A',
    alert_tier: 2,
    composite_score: 98,
    confidence: 0.92,
    model_count: 6,
    regime: 'TRANSITIONAL',
    categories: ['Large Cap'],
    reason: 'Strong consensus: 100% bearish',
    key_drivers: ['Strong consensus', 'Minervini 8/8'],
    model_ids: ['stage-scanner'],
    generated_at: new Date(Date.now() - 17 * 60_000).toISOString(),
    website: 'https://app.getsigna.ai/dashboard/best-trades',
  },
]

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn(() =>
    Promise.resolve({ ok: true, json: async () => SIGNALS } as Response)
  )
  vi.stubGlobal('fetch', fetchMock)
})

describe('SignaBestTradesWidget', () => {
  it('ranks signals by composite score and reveals metrics on expand', async () => {
    render(<SignaBestTradesWidget />)

    expect(screen.getByText(/signa · best trades/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('TOPPICK')).toBeInTheDocument()
    })

    // Highest score is ranked #1.
    const rankOne = screen.getByText('#1').closest('button')
    expect(rankOne?.textContent).toContain('TOPPICK')
    const rankTwo = screen.getByText('#2').closest('button')
    expect(rankTwo?.textContent).toContain('LOWER')

    // Collapsed: metric labels hidden until the card is expanded.
    expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument()

    fireEvent.click(rankOne as HTMLElement)

    expect(screen.getByText('92%')).toBeInTheDocument() // confidence metric
    expect(screen.getByText('Large Cap')).toBeInTheDocument() // category chip
    expect(screen.getByText(/open in signa/i)).toBeInTheDocument()
  })
})
