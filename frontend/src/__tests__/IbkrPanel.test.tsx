import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import IbkrPanel from '../components/IbkrPanel'
import type { IbkrTrade } from '../types'

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
})
