import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import IbkrPanel from '../components/IbkrPanel'
import type { IbkrStatus, IbkrTrade } from '../types'

const TRADE: IbkrTrade = {
  id: 1,
  exec_id: 'e1',
  account: 'U123',
  symbol: 'AAPL',
  sec_type: 'STK',
  currency: 'USD',
  side: 'BOT',
  quantity: 10,
  price: 198.5,
  commission: 1.2,
  executed_at: '2026-09-20T14:30:00Z',
  created_at: '2026-09-20T14:30:00Z',
}

describe('IbkrPanel', () => {
  it('labels the trades section as recent transactions, not today-only executions', () => {
    render(
      <IbkrPanel
        status={{ configured: true, connected: true, last_sync: null, last_error: null }}
        positions={[]}
        trades={[TRADE]}
        account={{}}
        loading={false}
        error={null}
        reload={vi.fn()}
      />,
    )

    expect(screen.getByText('Recent Transactions')).toBeInTheDocument()
    expect(screen.queryByText(/today/i)).not.toBeInTheDocument()
  })

  it('shows the trade date, not just the time', () => {
    render(
      <IbkrPanel
        status={{ configured: true, connected: true, last_sync: null, last_error: null }}
        positions={[]}
        trades={[TRADE]}
        account={{}}
        loading={false}
        error={null}
        reload={vi.fn()}
      />,
    )

    const expected = new Date(TRADE.executed_at as string).toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    })
    expect(screen.getByText(expected)).toBeInTheDocument()
  })

  it('shows an empty state without a "today" implication', () => {
    render(
      <IbkrPanel
        status={{ configured: true, connected: true, last_sync: null, last_error: null }}
        positions={[]}
        trades={[]}
        account={{}}
        loading={false}
        error={null}
        reload={vi.fn()}
      />,
    )

    expect(screen.getByText('No recent transactions.')).toBeInTheDocument()
  })

  function renderWithStatus(status: IbkrStatus, relogin = vi.fn(async () => {})) {
    render(
      <IbkrPanel
        status={status}
        positions={[]}
        trades={[]}
        account={{}}
        loading={false}
        error={null}
        reload={vi.fn()}
        relogin={relogin}
      />,
    )
    return relogin
  }

  const LOGGED_OUT: IbkrStatus = {
    configured: true,
    connected: false,
    state: 'logged_out',
    relogin_available: true,
    last_sync: '2026-10-23T15:23:00Z',
    last_error: 'IB Gateway lost its IBKR session',
  }

  it('says logged out, not connected, and offers a re-login', () => {
    const relogin = renderWithStatus(LOGGED_OUT)

    expect(screen.getByText('Logged out')).toBeInTheDocument()
    expect(screen.queryByText('Connected')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Re-login' }))
    expect(relogin).toHaveBeenCalledOnce()
  })

  it('hides the re-login button when the backend cannot restart the gateway', () => {
    renderWithStatus({ ...LOGGED_OUT, relogin_available: false })
    expect(screen.queryByRole('button', { name: 'Re-login' })).not.toBeInTheDocument()
  })

  it('asks for the 2FA approval while restarting', () => {
    renderWithStatus({ ...LOGGED_OUT, state: 'restarting' })

    expect(screen.getByText(/approve the IBKR 2FA prompt/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Re-login' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Error:/)).not.toBeInTheDocument()
  })

  it('falls back to the connected flag from older backends', () => {
    renderWithStatus({ configured: true, connected: true, last_sync: null, last_error: null })
    expect(screen.getByText('Connected')).toBeInTheDocument()
  })
})
