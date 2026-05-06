import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ForexMacroWidget from '../components/ForexMacroWidget'

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn(() =>
    Promise.resolve(
      {
        ok: true,
        json: async () => ({
          as_of: '2024-11-04T14:30:00Z',
          yield_curves: [
            {
              label: 'US',
              spread_2s10s: 0.42,
              points: [
                { maturity: '2Y', symbol: 'US02Y', yield_percent: 4.31 },
                { maturity: '10Y', symbol: 'US10Y', yield_percent: 4.73 },
              ],
            },
          ],
          crypto_indices: [
            {
              symbol: 'TOTAL',
              name: 'Total Crypto Market Cap',
              price: 2450000000000,
              change_percent: 1.25,
              category: 'crypto',
              website: 'https://www.tradingview.com/symbols/CRYPTOCAP-TOTAL/',
            },
          ],
          stock_forex_indices: [
            {
              symbol: 'SPY',
              name: 'SPY',
              price: 585.12,
              change_percent: 0.38,
              category: 'stock',
              website: 'https://www.tradingview.com/symbols/NYSE-SPY/',
            },
            {
              symbol: 'DXY',
              name: 'US Dollar Index',
              price: 104.23,
              change_percent: 0.18,
              category: 'forex',
              website: 'https://www.tradingview.com/symbols/DXY-Y/',
            },
          ],
          fx_indices: [
            {
              symbol: 'DXY',
              name: 'US Dollar Index',
              price: 104.23,
              change_percent: 0.18,
              website: 'https://www.tradingview.com/symbols/DXY-Y/',
            },
          ],
          stock_forex_visible: true,
          sources: {
            yield_curves: 'tradingview',
            crypto_indices: 'tradingview',
            stock_forex_indices: 'tradingview',
            fx_indices: 'tradingview',
          },
        }),
      } as Response
    )
  )
  vi.stubGlobal('fetch', fetchMock)
})

describe('ForexMacroWidget', () => {
  it('renders macro snapshot data from the API payload', async () => {
    render(<ForexMacroWidget />)

    expect(screen.getByText(/macro snapshot/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('US Yield Curve')).toBeInTheDocument()
      expect(screen.getByText('Crypto Indices')).toBeInTheDocument()
      expect(screen.getByText('Stock & Forex Indices')).toBeInTheDocument()
      expect(screen.getByText('US Dollar Index')).toBeInTheDocument()
      expect(screen.getByText('4.73%')).toBeInTheDocument()
    })
  })

  it('renders clickable index links to TradingView', async () => {
    render(<ForexMacroWidget />)

    await waitFor(() => {
      const spyLinks = screen.getAllByRole('link').filter((link) => link.getAttribute('href')?.includes('tradingview.com'))
      expect(spyLinks.length).toBeGreaterThan(0)
      
      // Verify specific links
      const spyLink = screen.getByRole('link', { name: /SPY/i })
      expect(spyLink).toHaveAttribute('href', 'https://www.tradingview.com/symbols/NYSE-SPY/')
      expect(spyLink).toHaveAttribute('target', '_blank')
    })
  })
})