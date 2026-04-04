import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SpyHeatmapWidget from '../components/SpyHeatmapWidget'

const samplePayload = {
  data: [
    {
      ticker: 'AAPL',
      sector: 'Technology',
      close: '190',
      prev_close: '185',
      marketcap: 2_900_000_000_000,
    },
    {
      ticker: 'MSFT',
      sector: 'Technology',
      close: '410',
      prev_close: '405',
      marketcap: 3_100_000_000_000,
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
  it('renders heatmap cells from API payload', async () => {
    render(<SpyHeatmapWidget />)

    await waitFor(() => {
      expect(screen.getByText(/spy heatmap/i)).toBeInTheDocument()
      expect(screen.getByText('AAPL')).toBeInTheDocument()
      expect(screen.getByText('MSFT')).toBeInTheDocument()
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
})
