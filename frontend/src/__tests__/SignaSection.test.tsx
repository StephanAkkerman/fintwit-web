import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SignaSection from '../components/SignaSection'

beforeEach(() => {
  // Both widgets fetch on mount; return an empty list for whichever is active.
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ ok: true, json: async () => [] } as Response))
  )
})

describe('SignaSection', () => {
  it('defaults to Best Trades and switches to the Live Feed tab', async () => {
    render(<SignaSection />)

    // Best Trades active by default.
    await waitFor(() =>
      expect(screen.getByText(/signa · best trades/i)).toBeInTheDocument()
    )
    expect(screen.queryByText(/signa · live feed/i)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /live feed/i }))

    await waitFor(() =>
      expect(screen.getByText(/signa · live feed/i)).toBeInTheDocument()
    )
    expect(screen.queryByText(/signa · best trades/i)).not.toBeInTheDocument()
  })
})
