import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StockMarketHoursBanner from '../components/StockMarketHoursBanner'

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn(() =>
    Promise.resolve(
      {
        ok: true,
        json: async () => [
          {
            exchange: 'NYSE',
            symbol: 'SPY',
            session: 'Pre-market',
            is_open: true,
            market_state: 'PRE',
            as_of: '2026-04-10T11:00:00+00:00',
            timezone: 'America/New_York',
            exchange_name: 'NYSE Arca',
          },
          {
            exchange: 'NASDAQ',
            symbol: 'QQQ',
            session: 'After-hours',
            is_open: true,
            market_state: 'POST',
            as_of: '2026-04-10T21:00:00+00:00',
            timezone: 'America/New_York',
            exchange_name: 'NASDAQ',
          },
        ],
      } as Response
    )
  )
  vi.stubGlobal('fetch', fetchMock)
})

describe('StockMarketHoursBanner', () => {
  it('renders exchange session badges from API payload', async () => {
    render(<StockMarketHoursBanner />)

    expect(screen.getByText(/major exchange sessions/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('NYSE')).toBeInTheDocument()
      expect(screen.getAllByText('NASDAQ').length).toBeGreaterThan(0)
    })

    expect(screen.getByText('Pre-market')).toBeInTheDocument()
    expect(screen.getByText('After-hours')).toBeInTheDocument()
  })
})
