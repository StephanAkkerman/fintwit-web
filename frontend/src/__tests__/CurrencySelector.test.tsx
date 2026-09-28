import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CurrencySelector from '../components/CurrencySelector'
import { CurrencyProvider, useCurrency } from '../contexts/CurrencyContext'

function Amount() {
  const { format } = useCurrency()
  return <span>{format(100)}</span>
}

describe('CurrencySelector + CurrencyProvider', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ base: 'USD', rates: { EUR: 0.5 } }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('converts displayed amounts when the currency changes', async () => {
    render(
      <CurrencyProvider>
        <CurrencySelector />
        <Amount />
      </CurrencyProvider>,
    )

    expect(screen.getByText('$100.00')).toBeInTheDocument()

    await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/fx/rates'))

    fireEvent.change(screen.getByLabelText('Display currency'), { target: { value: 'EUR' } })

    await waitFor(() => expect(screen.getByText('€50.00')).toBeInTheDocument())
  })
})
