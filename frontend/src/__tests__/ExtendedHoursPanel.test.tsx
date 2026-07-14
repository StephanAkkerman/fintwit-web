import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ExtendedHoursPanel from '../components/ExtendedHoursPanel'

const BASE_SNAPSHOT = {
  session: 'pre-market',
  window_start: '2026-06-23T04:00:00-04:00',
  window_end: '2026-06-23T09:30:00-04:00',
  futures: [
    { label: 'ES', symbol: 'CME_MINI:ES1!', price: 5800.0, change_pct: 0.31 },
    { label: 'NQ', symbol: 'CME_MINI:NQ1!', price: 20100.0, change_pct: 0.48 },
    { label: 'YM', symbol: 'CBOT_MINI:YM1!', price: 43000.0, change_pct: 0.22 },
  ],
  etfs: [
    { symbol: 'SPY', price: 580.0, extended_price: 581.5, extended_change_pct: 0.26 },
    { symbol: 'QQQ', price: 490.5, extended_price: 492.8, extended_change_pct: 0.47 },
    { symbol: 'IWM', price: 210.2, extended_price: null, extended_change_pct: null },
  ],
  tweet_stats: {
    total_mentions: 42,
    top_tickers: [{ ticker: 'NVDA', mentions: 10, sentiment: 'BULL' }],
    sentiment_distribution: { BULL: 20, BEAR: 10, NEUTRAL: 12 },
  },
}

function mockFetch(snapshot: object) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve({ ok: true, json: async () => snapshot } as Response)
    )
  )
}

describe('ExtendedHoursPanel', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('renders nothing during regular session', async () => {
    mockFetch({ ...BASE_SNAPSHOT, session: 'regular' })
    const { container } = render(<ExtendedHoursPanel />)
    await waitFor(() => expect(container.firstChild).toBeNull())
  })

  it('renders full panel during pre-market', async () => {
    mockFetch(BASE_SNAPSHOT)
    render(<ExtendedHoursPanel />)
    await waitFor(() => {
      expect(screen.getByText('Pre-market')).toBeInTheDocument()
      expect(screen.getByText('ES')).toBeInTheDocument()
      expect(screen.getByText('NQ')).toBeInTheDocument()
      expect(screen.getByText('SPY')).toBeInTheDocument()
      expect(screen.getByText('NVDA')).toBeInTheDocument()
      expect(screen.getByText(/42 mentions/)).toBeInTheDocument()
    })
  })

  it('renders full panel during after-hours', async () => {
    mockFetch({ ...BASE_SNAPSHOT, session: 'after-hours' })
    render(<ExtendedHoursPanel />)
    await waitFor(() => {
      expect(screen.getByText('After-hours')).toBeInTheDocument()
    })
  })

  it('renders collapsed chip during closed session and expands on click', async () => {
    mockFetch({ ...BASE_SNAPSHOT, session: 'closed' })
    render(<ExtendedHoursPanel />)

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /last session/i })).toBeInTheDocument()
    )

    fireEvent.click(screen.getByRole('button', { name: /last session/i }))

    await waitFor(() => {
      expect(screen.getByText('ES')).toBeInTheDocument()
    })
  })

  it('shows green for positive futures change', async () => {
    mockFetch(BASE_SNAPSHOT)
    render(<ExtendedHoursPanel />)
    await waitFor(() => screen.getByText('+0.31%'))
    const pct = screen.getByText('+0.31%')
    expect(pct.className).toMatch(/emerald|green/)
  })
})
