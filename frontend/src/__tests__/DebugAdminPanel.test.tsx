import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DebugAdminPanel from '../components/DebugAdminPanel'

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn(() =>
    Promise.resolve({
      ok: true,
      json: async () => ({ id: 12345, text: 'Injected $AAPL', tickers: ['AAPL'], hashtags: ['BTC'] }),
    } as Response)
  )
  vi.stubGlobal('fetch', fetchMock)
})

describe('DebugAdminPanel', () => {
  it('posts debug tweet payload and shows success state', async () => {
    render(<DebugAdminPanel />)

    fireEvent.change(screen.getByLabelText('Debug tweet text'), {
      target: { value: 'Injected $AAPL and #BTC' },
    })
    fireEvent.change(screen.getByLabelText('Debug tickers'), { target: { value: 'AAPL,BTC' } })
    fireEvent.change(screen.getByLabelText('Debug hashtags'), { target: { value: 'btc' } })

    fireEvent.click(screen.getByRole('button', { name: /inject debug tweet/i }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/debug/tweet',
        expect.objectContaining({ method: 'POST' })
      )
    })

    await waitFor(() => {
      expect(screen.getByText(/debug tweet injected successfully/i)).toBeInTheDocument()
      expect(screen.getByText(/last injected tweet/i)).toBeInTheDocument()
      expect(screen.getByText(/id: 12345/i)).toBeInTheDocument()
    })
  })
})
