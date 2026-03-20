import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

// Stub fetch and EventSource so the hook doesn't throw in jsdom
class MockEventSource {
  onmessage: null = null
  onerror: null = null
  close = vi.fn()
  constructor(_url: string, _init?: EventSourceInit) {}
}

beforeEach(() => {
  vi.stubGlobal('EventSource', MockEventSource)
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ json: async () => [] } as unknown as Response)
  )
})

describe('App', () => {
  it('renders the X Stream heading', async () => {
    render(<App />)
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /x stream/i })).toBeInTheDocument()
    )
  })

  it('renders the live tweets subtitle', async () => {
    render(<App />)
    await waitFor(() =>
      expect(screen.getByText(/live tweets/i)).toBeInTheDocument()
    )
  })
})
