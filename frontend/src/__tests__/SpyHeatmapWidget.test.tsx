import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SpyHeatmapWidget from '../components/SpyHeatmapWidget'

const samplePayload = {
  data: [
    {
      ticker: 'AAPL',
      sector: 'Technology',
      industry: 'Consumer Electronics',
      close: '190',
      prev_close: '185',
      marketcap: 2_900_000_000_000,
    },
    {
      ticker: 'MSFT',
      sector: 'Technology',
      industry: 'Software Infrastructure',
      close: '410',
      prev_close: '405',
      marketcap: 3_100_000_000_000,
    },
    {
      ticker: 'JPM',
      sector: 'Financial Services',
      industry: 'Banks',
      close: '190',
      prev_close: '198',
      marketcap: 550_000_000_000,
    },
  ],
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn(() =>
    Promise.resolve({ ok: true, json: async () => samplePayload } as Response)
  )
  vi.stubGlobal('fetch', fetchMock)
})

describe('SpyHeatmapWidget', () => {
  it('renders the whole market as nested sector/industry/ticker boxes', async () => {
    render(<SpyHeatmapWidget />)

    await waitFor(() => {
      expect(screen.getByText(/market heatmap/i)).toBeInTheDocument()
      expect(screen.getByText('Technology')).toBeInTheDocument()
      expect(screen.getByText('Financial Services')).toBeInTheDocument()
      expect(screen.getByText('AAPL')).toBeInTheDocument()
      expect(screen.getByText('MSFT')).toBeInTheDocument()
      expect(screen.getByText('JPM')).toBeInTheDocument()
    })
  })

  it('fetches a new range when a range button is clicked', async () => {
    render(<SpyHeatmapWidget />)

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled()
    })

    fireEvent.click(screen.getByRole('button', { name: '1W' }))

    await waitFor(() => {
      const calledOneWeek = fetchMock.mock.calls.some(([arg]) =>
        String(arg).includes('/api/spy-heatmap?date=one_week')
      )
      expect(calledOneWeek).toBe(true)
    })
  })

  it('drills into a sector on click and shows a breadcrumb back to Market', async () => {
    render(<SpyHeatmapWidget />)

    await waitFor(() => expect(screen.getByText('Technology')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /show technology sector in detail/i }))

    await waitFor(() => {
      expect(screen.getByText('Consumer Electronics')).toBeInTheDocument()
      expect(screen.getByText('Software Infrastructure')).toBeInTheDocument()
      expect(screen.queryByText('Financial Services')).not.toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Market' }))

    await waitFor(() => {
      expect(screen.getByText('Technology')).toBeInTheDocument()
      expect(screen.getByText('Financial Services')).toBeInTheDocument()
    })
  })

  it('drills straight into a subsector from the market view', async () => {
    render(<SpyHeatmapWidget />)

    await waitFor(() => expect(screen.getByText('Technology')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /show consumer electronics in detail/i }))

    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument()
      expect(screen.queryByText('MSFT')).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Technology' })).toBeInTheDocument()
    })
  })
})
