import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MarketMoversExplorer from '../components/MarketMoversExplorer'

const GAINER = {
  symbol: 'AAPL',
  name: 'Apple Inc.',
  price: 185.0,
  change_pct: 1.23,
  volume: 1_200_000,
  market_cap: 3e12,
}
const LOSER = {
  symbol: 'TSLA',
  name: 'Tesla Inc.',
  price: 200.0,
  change_pct: -0.87,
  volume: 850_000,
  market_cap: 6e11,
}
const CRYPTO_GAINER = {
  symbol: 'DOGEUSD',
  name: 'Dogecoin',
  price: 0.12,
  change_pct: 4.5,
  volume: 500_000,
  market_cap: 1.5e10,
}

function mockFetchByQuery() {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: string | URL | Request) => {
      const url = new URL(String(input), 'http://localhost')
      const market = url.searchParams.get('market')
      const category = url.searchParams.get('category')

      let movers: object[] = [GAINER]
      if (category === 'losers') movers = [LOSER]
      if (market === 'crypto') movers = [CRYPTO_GAINER]

      return Promise.resolve({
        ok: true,
        json: async () => ({ market, category, movers }),
      } as Response)
    })
  )
}

describe('MarketMoversExplorer', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('fetches USA gainers by default and renders the table', async () => {
    mockFetchByQuery()
    render(<MarketMoversExplorer />)

    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument()
    })
    expect(fetch).toHaveBeenCalledWith(
      '/api/markets/movers?market=usa&category=gainers',
      expect.anything()
    )
  })

  it('formats positive change as green and negative as red', async () => {
    mockFetchByQuery()
    render(<MarketMoversExplorer />)

    await waitFor(() => {
      const pct = screen.getByText('+1.23%')
      expect(pct.className).toMatch(/emerald|green/)
    })

    fireEvent.click(screen.getByRole('tab', { name: 'Losers' }))

    await waitFor(() => {
      const pct = screen.getByText('-0.87%')
      expect(pct.className).toMatch(/red/)
    })
  })

  it('refetches when switching the category tab', async () => {
    mockFetchByQuery()
    render(<MarketMoversExplorer />)

    await waitFor(() => expect(screen.getByText('AAPL')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('tab', { name: 'Losers' }))

    await waitFor(() => expect(screen.getByText('TSLA')).toBeInTheDocument())
    expect(fetch).toHaveBeenCalledWith(
      '/api/markets/movers?market=usa&category=losers',
      expect.anything()
    )
  })

  it('refetches when switching the market dropdown', async () => {
    mockFetchByQuery()
    render(<MarketMoversExplorer />)

    await waitFor(() => expect(screen.getByText('AAPL')).toBeInTheDocument())

    fireEvent.change(screen.getByLabelText('Market'), { target: { value: 'crypto' } })

    await waitFor(() => expect(screen.getByText('DOGEUSD')).toBeInTheDocument())
    expect(fetch).toHaveBeenCalledWith(
      '/api/markets/movers?market=crypto&category=gainers',
      expect.anything()
    )
  })

  it('shows an error message when the fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false } as Response)))
    render(<MarketMoversExplorer />)

    await waitFor(() => {
      expect(screen.getByText(/could not load market movers/i)).toBeInTheDocument()
    })
  })

  it('shows an empty state when there are no movers', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: async () => ({ market: 'usa', category: 'gainers', movers: [] }),
        } as Response)
      )
    )
    render(<MarketMoversExplorer />)

    await waitFor(() => {
      expect(screen.getByText(/no movers found/i)).toBeInTheDocument()
    })
  })
})
