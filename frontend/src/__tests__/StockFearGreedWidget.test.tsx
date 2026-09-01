import { render, screen, waitFor } from '@testing-library/react'
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
})
