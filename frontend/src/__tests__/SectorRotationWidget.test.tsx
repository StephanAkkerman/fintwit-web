import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SectorRotationWidget from '../components/SectorRotationWidget'

function trail(rsRatio: number, rsMomentum: number) {
  return Array.from({ length: 5 }, (_, i) => ({
    date: `2026-09-0${i + 1}`,
    rs_ratio: rsRatio - (4 - i) * 0.1,
    rs_momentum: rsMomentum - (4 - i) * 0.1,
  }))
}

const samplePayload = {
  timeframe: 'daily',
  benchmark: 'SPY',
  window: 14,
  sectors: [
    {
      sector: 'Technology',
      etf: 'XLK',
      quadrant: 'leading',
      trail: trail(103.5, 102.1),
    },
    {
      sector: 'Health Care',
      etf: 'XLV',
      quadrant: 'lagging',
      trail: trail(97.2, 98.4),
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

describe('SectorRotationWidget', () => {
  it('renders sector legend chips and quadrant summary from the API payload', async () => {
    render(<SectorRotationWidget />)

    await waitFor(() => {
      expect(screen.getByText(/sector rotation/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /XLK/ })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /XLV/ })).toBeInTheDocument()
    })

    expect(screen.getByTestId('quadrant-summary-leading')).toHaveTextContent('Technology')
    expect(screen.getByTestId('quadrant-summary-lagging')).toHaveTextContent('Health Care')
  })

  it('toggles a sector out of the chart/summary when its legend chip is clicked', async () => {
    render(<SectorRotationWidget />)

    await waitFor(() => expect(screen.getByRole('button', { name: /XLK/ })).toBeInTheDocument())

    const techChip = screen.getByRole('button', { name: /XLK/ })
    expect(techChip).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(techChip)

    expect(techChip).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByTestId('quadrant-summary-leading')).toHaveTextContent('—')
  })

  it('fetches a new timeframe when the Weekly button is clicked', async () => {
    render(<SectorRotationWidget />)

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())

    fireEvent.click(screen.getByRole('button', { name: 'Weekly' }))

    await waitFor(() => {
      const calledWeekly = fetchMock.mock.calls.some(([arg]) =>
        String(arg).includes('/api/sector-rotation?timeframe=weekly')
      )
      expect(calledWeekly).toBe(true)
    })
  })

  it('exposes the latest reading for every sector through a table view', async () => {
    render(<SectorRotationWidget />)

    await waitFor(() => expect(screen.getByRole('button', { name: /XLK/ })).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /show table view/i }))

    expect(screen.getByText('103.50')).toBeInTheDocument()
    expect(screen.getByText('98.40')).toBeInTheDocument()
  })

  it('shows an empty state when there is no sector data', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ timeframe: 'daily', benchmark: 'SPY', window: 14, sectors: [] }),
    } as Response)

    render(<SectorRotationWidget />)

    await waitFor(() => {
      expect(screen.getByText(/no sector rotation data available/i)).toBeInTheDocument()
    })
  })

  it('surfaces a load error', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, json: async () => ({}) } as Response)

    render(<SectorRotationWidget />)

    await waitFor(() => {
      expect(screen.getByText(/could not load sector rotation data/i)).toBeInTheDocument()
    })
  })
})
