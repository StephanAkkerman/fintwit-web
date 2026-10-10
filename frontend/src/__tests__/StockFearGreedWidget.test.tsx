import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StockFearGreedWidget from '../components/StockFearGreedWidget'

let fetchMock: ReturnType<typeof vi.fn>

function stubFetch(response: Partial<Response>) {
  fetchMock = vi.fn(() => Promise.resolve(response as Response))
  vi.stubGlobal('fetch', fetchMock)
}

describe('StockFearGreedWidget', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the value, status and change from the API payload', async () => {
    stubFetch({
      ok: true,
      json: async () => ({ value: 54, status: 'Neutral', change: '+8.0% 📈' }),
    })

    render(<StockFearGreedWidget />)

    await waitFor(() => {
      expect(screen.getByText('54')).toBeInTheDocument()
    })

    expect(screen.getByText('Neutral')).toBeInTheDocument()
    expect(screen.getByText('+8.0% 📈')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/stocks/fear-greed', expect.anything())
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/stocks/fear-greed/history?days=30',
      expect.anything(),
    )
  })

  it('omits the change line when the API does not report one', async () => {
    stubFetch({
      ok: true,
      json: async () => ({ value: 30, status: 'Fear', change: null }),
    })

    render(<StockFearGreedWidget />)

    await waitFor(() => {
      expect(screen.getByText('30')).toBeInTheDocument()
    })

    expect(screen.getByText('Fear')).toBeInTheDocument()
  })

  it('shows an error message when the request fails', async () => {
    stubFetch({ ok: false })

    render(<StockFearGreedWidget />)

    await waitFor(() => {
      expect(screen.getByText(/could not load the fear/i)).toBeInTheDocument()
    })
  })

  it('treats an unfixtured catch-all array response as an error, not a crash', async () => {
    stubFetch({ ok: true, json: async () => [] })

    render(<StockFearGreedWidget />)

    await waitFor(() => {
      expect(screen.getByText(/could not load the fear/i)).toBeInTheDocument()
    })
  })

  it('refetches the history when switching to the 7d window', async () => {
    fetchMock = vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        json: async () =>
          url.includes('/history')
            ? {
                days: url.endsWith('days=7') ? 7 : 30,
                source: 'cnn',
                points: [
                  { date: '2026-10-01', value: 40 },
                  { date: '2026-10-08', value: 55 },
                ],
              }
            : { value: 55, status: 'Neutral', change: null },
      } as Response),
    )
    vi.stubGlobal('fetch', fetchMock)

    render(<StockFearGreedWidget />)

    await waitFor(() => {
      expect(screen.getByTestId('fear-greed-history')).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: '30d' })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: '7d' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/stocks/fear-greed/history?days=7',
        expect.anything(),
      )
    })
    expect(screen.getByRole('button', { name: '7d' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('keeps the current reading when only the history fails', async () => {
    fetchMock = vi.fn((url: string) =>
      Promise.resolve(
        (url.includes('/history')
          ? { ok: false }
          : { ok: true, json: async () => ({ value: 22, status: 'Extreme Fear' }) }) as Response,
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    render(<StockFearGreedWidget />)

    await waitFor(() => {
      expect(screen.getByText('22')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText(/history unavailable/i)).toBeInTheDocument()
    })
  })
})
