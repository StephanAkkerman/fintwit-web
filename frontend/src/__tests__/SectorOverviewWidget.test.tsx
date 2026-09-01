import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SectorOverviewWidget from '../components/SectorOverviewWidget'

const samplePayload = {
  sectors: [
    {
      sector: 'Technology',
      market_cap: 4_000_000_000_000,
      change_percent: 1.5,
      stock_count: 2,
      subsectors: [
        {
          industry: 'Semiconductors',
          market_cap: 3_000_000_000_000,
          change_percent: 2.1,
          stock_count: 1,
        },
        {
          industry: 'Software',
          market_cap: 1_000_000_000_000,
          change_percent: -0.5,
          stock_count: 1,
        },
      ],
    },
    {
      sector: 'Financials',
      market_cap: 500_000_000_000,
      change_percent: -0.8,
      stock_count: 1,
      subsectors: [
        {
          industry: 'Other',
          market_cap: 500_000_000_000,
          change_percent: -0.8,
          stock_count: 1,
        },
      ],
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

describe('SectorOverviewWidget', () => {
  it('renders sector rows from the API payload', async () => {
    render(<SectorOverviewWidget />)

    await waitFor(() => {
      expect(screen.getByText(/sector overview/i)).toBeInTheDocument()
      expect(screen.getByText('Technology')).toBeInTheDocument()
      expect(screen.getByText('Financials')).toBeInTheDocument()
      expect(screen.getByText('+1.50%')).toBeInTheDocument()
    })
  })

  it('expands a sector with a real subsector breakdown to show its industries', async () => {
    render(<SectorOverviewWidget />)

    await waitFor(() => expect(screen.getByText('Technology')).toBeInTheDocument())

    expect(screen.queryByText('Semiconductors')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('Technology'))

    await waitFor(() => {
      expect(screen.getByText('Semiconductors')).toBeInTheDocument()
      expect(screen.getByText('Software')).toBeInTheDocument()
      expect(screen.getByText('+2.10%')).toBeInTheDocument()
    })
  })

  it('does not offer to expand a sector whose only subsector is "Other"', async () => {
    render(<SectorOverviewWidget />)

    await waitFor(() => expect(screen.getByText('Financials')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Financials'))

    expect(screen.queryByText('Other')).not.toBeInTheDocument()
  })

  it('fetches a new range when a range button is clicked', async () => {
    render(<SectorOverviewWidget />)

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled()
    })

    fireEvent.click(screen.getByRole('button', { name: '1M' }))

    await waitFor(() => {
      const calledOneMonth = fetchMock.mock.calls.some(([arg]) =>
        String(arg).includes('/api/spy-heatmap/sectors?date=one_month')
      )
      expect(calledOneMonth).toBe(true)
    })
  })
})
