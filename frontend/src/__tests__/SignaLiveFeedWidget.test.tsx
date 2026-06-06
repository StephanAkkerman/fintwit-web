import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SignaLiveFeedWidget from '../components/SignaLiveFeedWidget'
import type { SignaLiveSignal } from '../types'

const SIGNALS: SignaLiveSignal[] = [
  {
    source: 'signa',
    id: 'weak',
    symbol: 'WEAK',
    signal: 'BUY',
    direction: 'BULLISH',
    model_name: 'MacdAgent',
    category: 'technical',
    confidence: 0.5,
    reason: 'A weaker setup',
    entry_price: 10,
    score: 80,
    tier: 1,
    created_at: new Date(Date.now() - 9 * 60_000).toISOString(),
    website: 'https://app.getsigna.ai/chart?sym=WEAK',
  },
  {
    source: 'signa',
    id: 'top',
    symbol: 'TOPPICK',
    signal: 'SHORT',
    direction: 'BEARISH',
    grade: 'A',
    model_name: 'TrendBreakAgent',
    category: 'technical',
    confidence: 0.92,
    reason: 'Breakdown below support',
    entry_price: 42.5,
    score: 98,
    tier: 1,
    created_at: new Date(Date.now() - 3 * 60_000).toISOString(),
    website: 'https://app.getsigna.ai/chart?sym=TOPPICK',
  },
]

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn(() =>
    Promise.resolve({ ok: true, json: async () => SIGNALS } as Response)
  )
  vi.stubGlobal('fetch', fetchMock)
})

describe('SignaLiveFeedWidget', () => {
  it('ranks directional signals by score and reveals trade metrics on expand', async () => {
    render(<SignaLiveFeedWidget />)

    expect(screen.getByText(/signa · live feed/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('TOPPICK')).toBeInTheDocument()
    })

    // Highest score ranked #1.
    const rankOne = screen.getByText('#1').closest('button')
    expect(rankOne?.textContent).toContain('TOPPICK')
    const rankTwo = screen.getByText('#2').closest('button')
    expect(rankTwo?.textContent).toContain('WEAK')

    // Collapsed: trade metric labels hidden until expanded.
    expect(screen.queryByText(/^Entry$/)).not.toBeInTheDocument()

    fireEvent.click(rankOne as HTMLElement)

    expect(screen.getByText('92%')).toBeInTheDocument() // confidence metric
    expect(screen.getByText('$42.50')).toBeInTheDocument() // entry price
    expect(screen.getByText(/open in signa/i)).toBeInTheDocument()
  })

  it('requests the live-feed endpoint', async () => {
    render(<SignaLiveFeedWidget />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(fetchMock.mock.calls[0][0]).toContain('/api/signa/live-feed')
  })
})
