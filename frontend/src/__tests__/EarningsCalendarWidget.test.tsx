import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EarningsCalendarWidget from '../components/EarningsCalendarWidget'

let fetchMock: ReturnType<typeof vi.fn>

const PAYLOAD = {
  start_date: '2026-09-03',
  end_date: '2026-09-04',
  days: [
    {
      date: '2026-09-03',
      count: 1,
      rows: [
        {
          symbol: 'AAPL',
          name: 'Apple Inc.',
          date: '2026-09-03',
          session: 'after-hours',
          session_emoji: '🌙',
          market_cap: 3_000_000_000_000,
          eps_forecast: 1.25,
          num_estimates: 12,
          fiscal_quarter_ending: 'Sep/2026',
          last_year_eps: 1.1,
          last_year_report_date: '08/01/2025',
          website: 'https://www.nasdaq.com/market-activity/stocks/aapl/earnings',
        },
      ],
    },
    {
      date: '2026-09-04',
      count: 0,
      rows: [],
    },
  ],
  source: 'nasdaq',
}

beforeEach(() => {
  fetchMock = vi.fn(() =>
    Promise.resolve({ ok: true, json: async () => PAYLOAD } as Response)
  )
  vi.stubGlobal('fetch', fetchMock)
})

describe('EarningsCalendarWidget', () => {
  it('renders earnings rows from the API payload', async () => {
    render(<EarningsCalendarWidget />)

    expect(screen.getByText(/earnings calendar/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument()
    })

    // Emoji + EPS estimate render as sibling text nodes in the same span.
    expect(
      screen.getByText((_, el) => el?.textContent === '🌙$1.25 est.')
    ).toBeInTheDocument()
    expect(screen.getByText('No major earnings')).toBeInTheDocument()
  })

  it('shows a portfolio badge only for held tickers', async () => {
    const portfolioLookup = (symbol: string) => (symbol === 'AAPL' ? ('active' as const) : null)
    render(<EarningsCalendarWidget portfolioLookup={portfolioLookup} />)

    await waitFor(() => {
      expect(screen.getByLabelText('Currently in your portfolio')).toBeInTheDocument()
    })
  })

  it('shows an error message when the fetch fails', async () => {
    fetchMock.mockImplementation(() => Promise.resolve({ ok: false } as Response))
    render(<EarningsCalendarWidget />)

    await waitFor(() => {
      expect(screen.getByText(/could not load the earnings calendar/i)).toBeInTheDocument()
    })
  })
})
