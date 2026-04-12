import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EconomicEventsWidget from '../components/EconomicEventsWidget'

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn(() =>
    Promise.resolve(
      {
        ok: true,
        json: async () => [
          {
            id: '1001',
            date: '11/04/2024',
            time: '14:30',
            zone: 'united states',
            currency: 'USD',
            event: 'Nonfarm Payrolls',
            actual: '250K',
            forecast: '230K',
            previous: '210K',
            impact_score: 3,
            impact_emoji: '🟥',
            source: 'https://www.investing.com/economic-calendar/',
          },
        ],
      } as Response
    )
  )
  vi.stubGlobal('fetch', fetchMock)
})

describe('EconomicEventsWidget', () => {
  it('renders events from API payload', async () => {
    render(<EconomicEventsWidget />)

    expect(screen.getByText(/economic events/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('Nonfarm Payrolls')).toBeInTheDocument()
      expect(screen.getByText('🇺🇸')).toBeInTheDocument()
      expect(screen.getByText('🟥')).toBeInTheDocument()
    })

    expect(screen.getByText('250K | 230K | 210K')).toBeInTheDocument()
  })
})
