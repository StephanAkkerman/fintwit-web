import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AccessAllowlistPanel from '../components/AccessAllowlistPanel'

let fetchMock: ReturnType<typeof vi.fn>

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status < 400,
    status,
    json: async () => body,
  } as Response
}

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

describe('AccessAllowlistPanel', () => {
  it('loads and lists the current allowlist', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ emails: ['owner@example.com'] }))

    render(<AccessAllowlistPanel />)

    await waitFor(() => {
      expect(screen.getByText('owner@example.com')).toBeInTheDocument()
    })
    expect(fetchMock).toHaveBeenCalledWith('/api/admin/access-emails')
  })

  it('invites a new email and shows it in the list', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ emails: [] }))
      .mockResolvedValueOnce(jsonResponse({ emails: ['friend@example.com'] }))

    render(<AccessAllowlistPanel />)
    await waitFor(() => {
      expect(screen.getByText(/no one is allowed in yet/i)).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText('Email to invite'), {
      target: { value: 'friend@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /invite/i }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/admin/access-emails',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ email: 'friend@example.com' }),
        })
      )
    })
    await waitFor(() => {
      expect(screen.getByText('friend@example.com')).toBeInTheDocument()
    })
  })

  it('removes an email from the list', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ emails: ['friend@example.com'] }))
      .mockResolvedValueOnce(jsonResponse({ emails: [] }))

    render(<AccessAllowlistPanel />)
    await waitFor(() => {
      expect(screen.getByText('friend@example.com')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByLabelText('Remove friend@example.com'))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/admin/access-emails/friend%40example.com',
        expect.objectContaining({ method: 'DELETE' })
      )
    })
    await waitFor(() => {
      expect(screen.getByText(/no one is allowed in yet/i)).toBeInTheDocument()
    })
  })

  it('shows a message when Cloudflare Access is not configured', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: "Cloudflare Access isn't configured on this deployment" }, 503)
    )

    render(<AccessAllowlistPanel />)

    await waitFor(() => {
      expect(screen.getByText(/isn't configured/i)).toBeInTheDocument()
    })
    expect(screen.queryByLabelText('Email to invite')).not.toBeInTheDocument()
  })
})
