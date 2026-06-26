import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MarketMoversPanel from '../components/MarketMoversPanel'

const GAINER = {
  symbol: 'AAPL', name: 'Apple Inc.', price: 185.0,
  extended_price: 186.28, change_pct: 1.23, volume: 1_200_000, market_cap: 3e12,
}
const LOSER = {
  symbol: 'TSLA', name: 'Tesla Inc.', price: 200.0,
  extended_price: 198.26, change_pct: -0.87, volume: 850_000, market_cap: 6e11,
}

function makeSnapshot(overrides: object = {}) {
  return { session_type: 'pre-market', gainers: [GAINER], losers: [LOSER], ...overrides }
}

function mockFetch(snapshot: object) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ ok: true, json: async () => snapshot } as Response))
  )
}

describe('MarketMoversPanel', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('renders null while loading', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    const { container } = render(<MarketMoversPanel />)
    expect(container.firstChild).toBeNull()
  })

  it('renders gainers and losers columns', async () => {
    mockFetch(makeSnapshot())
    render(<MarketMoversPanel />)
    await waitFor(() => {
      expect(screen.getByText('Gainers')).toBeInTheDocument()
      expect(screen.getByText('Losers')).toBeInTheDocument()
      expect(screen.getByText('AAPL')).toBeInTheDocument()
      expect(screen.getByText('TSLA')).toBeInTheDocument()
    })
  })

  it('shows pre-market badge for pre-market session_type', async () => {
    mockFetch(makeSnapshot({ session_type: 'pre-market' }))
    render(<MarketMoversPanel />)
    await waitFor(() => {
      const badge = screen.getByText('Pre-market')
      expect(badge.className).toMatch(/amber/)
    })
  })

  it('shows after-hours badge for after-hours session_type', async () => {
    mockFetch(makeSnapshot({ session_type: 'after-hours' }))
    render(<MarketMoversPanel />)
    await waitFor(() => {
      const badge = screen.getByText('After-hours')
      expect(badge.className).toMatch(/violet/)
    })
  })

  it('formats positive change as green', async () => {
    mockFetch(makeSnapshot())
    render(<MarketMoversPanel />)
    await waitFor(() => {
      const pct = screen.getByText('+1.23%')
      expect(pct.className).toMatch(/emerald|green/)
    })
  })

  it('formats negative change as red', async () => {
    mockFetch(makeSnapshot())
    render(<MarketMoversPanel />)
    await waitFor(() => {
      const pct = screen.getByText('-0.87%')
      expect(pct.className).toMatch(/red/)
    })
  })
})
