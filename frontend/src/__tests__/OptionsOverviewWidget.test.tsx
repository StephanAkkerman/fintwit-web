import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import OptionsOverviewWidget from '../components/OptionsOverviewWidget'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('OptionsOverviewWidget', () => {
  it('renders options totals and contracts from api payload', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: async () => ({
            symbols: [],
            totals: {
              call_volume: 1500,
              put_volume: 900,
              total_volume: 2400,
              put_call_ratio: 0.6,
            },
            bullish: [],
            bearish: [],
            most_active_contracts: [
              {
                symbol: 'AAPL',
                contract_type: 'CALL',
                expiry_date: 'Apr 17, 2026',
                strike: 200,
                volume: 1500,
                open_interest: 3200,
                website: 'https://www.nasdaq.com/market-activity/stocks/aapl/option-chain',
              },
            ],
            source: 'nasdaq',
          }),
        } as Response)
      )
    )

    render(<OptionsOverviewWidget />)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /options overview/i })).toBeInTheDocument()
      expect(screen.getAllByText(/1[.,]500/).length).toBeGreaterThan(0)
      expect(screen.getByText('900')).toBeInTheDocument()
      expect(screen.getByText('0.60')).toBeInTheDocument()
      expect(screen.getByRole('link', { name: 'AAPL' })).toBeInTheDocument()
    })
  })

  it('renders error state when fetch fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: false, json: async () => ({}) } as Response))
    )

    render(<OptionsOverviewWidget />)

    await waitFor(() => {
      expect(screen.getByText(/could not load options overview/i)).toBeInTheDocument()
    })
  })
})
