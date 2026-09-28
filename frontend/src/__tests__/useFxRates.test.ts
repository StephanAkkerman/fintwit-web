import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useFxRates } from '../hooks/useFxRates'

describe('useFxRates', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('loads FX rates on mount', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ base: 'USD', rates: { EUR: 0.92, GBP: 0.79 } }),
    } as Response)

    const { result } = renderHook(() => useFxRates())

    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.fxRates).toEqual({ base: 'USD', rates: { EUR: 0.92, GBP: 0.79 } })
    expect(result.current.error).toBeNull()
  })

  it('surfaces a load error', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 503 } as Response)

    const { result } = renderHook(() => useFxRates())

    await waitFor(() => expect(result.current.error).toMatch(/503/))
    expect(result.current.fxRates).toBeNull()
  })
})
