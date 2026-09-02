import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useTickerTimeseries } from '../hooks/useTickerTimeseries'
import type { TickerTimeseries } from '../types'

const SAMPLE: TickerTimeseries = {
  ticker: 'AAPL',
  window_hours: 168,
  bucket_hours: 6,
  points: [
    { bucket: '2026-01-01T00:00:00Z', mentions: 3, bullish: 2, bearish: 1, neutral: 0, avg_sentiment: 0.2 },
  ],
  summary: {
    total_mentions: 3,
    avg_mentions_per_bucket: 3,
    bullish: 2,
    bearish: 1,
    neutral: 0,
    avg_sentiment: 0.2,
    sentiment_label: 'BULL',
    unique_authors: 2,
    chart_mentions: 1,
    avg_engagement: 10,
    asset_kind: 'EQUITY',
    price_direction: 1.5,
    first_seen: '2026-01-01T00:00:00Z',
    last_seen: '2026-01-07T00:00:00Z',
  },
}

describe('useTickerTimeseries', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('does not fetch when ticker is null', () => {
    const { result } = renderHook(() => useTickerTimeseries(null))
    expect(fetch).not.toHaveBeenCalled()
    expect(result.current.data).toBeNull()
    expect(result.current.loading).toBe(false)
  })

  it('fetches the timeseries for the given ticker and window', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => SAMPLE } as Response)

    const { result } = renderHook(() => useTickerTimeseries('AAPL', 168))

    await waitFor(() => expect(result.current.data).toEqual(SAMPLE))
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/overview/ticker-timeseries?ticker=AAPL&window_hours=168'),
      expect.anything(),
    )
  })

  it('sets error when the request fails', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false } as Response)

    const { result } = renderHook(() => useTickerTimeseries('AAPL'))

    await waitFor(() => expect(result.current.error).toBe(true))
    expect(result.current.data).toBeNull()
  })

  it('re-fetches when the ticker changes', async () => {
    vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => SAMPLE } as Response)

    const { rerender } = renderHook(({ ticker }) => useTickerTimeseries(ticker), {
      initialProps: { ticker: 'AAPL' as string | null },
    })

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))

    rerender({ ticker: 'MSFT' })

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect(fetch).toHaveBeenLastCalledWith(
      expect.stringContaining('ticker=MSFT'),
      expect.anything(),
    )
  })
})
