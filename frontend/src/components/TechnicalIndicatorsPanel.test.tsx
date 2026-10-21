import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TechnicalIndicatorsPanel, { indicatorsKind } from './TechnicalIndicatorsPanel'
import { _resetIndicatorsCacheForTests } from '../hooks/useTechnicalIndicators'
import type { TechnicalIndicators } from '../types'

const EWZ: TechnicalIndicators = {
  symbol: 'EWZ',
  source: 'tradingview',
  tv_symbol: 'AMEX:EWZ',
  type: 'etf',
  price: 42.94,
  rsi: { value: 72.4, state: 'overbought', four_h: 63.7 },
  macd: { macd: 1.41, signal: 1.39, histogram: 0.02, above_signal: true, cross: 'bullish' },
  moving_averages: {
    sma20: 40.4,
    sma50: 37.95,
    sma200: 37.04,
    price_vs_sma20_percent: 6.27,
    price_vs_sma50_percent: 13.15,
    price_vs_sma200_percent: -1.5,
    sma50_vs_sma200: 'golden_cross',
    cross_today: null,
  },
  atr: { value: 1.02, percent_of_price: 2.38 },
  adx: { value: 30.9, trend_strength: 'strong', direction: 'up' },
  volume: { today: 60_000_000, avg_30d: 40_000_000, vs_avg_30d: 1.58 },
  rating: { one_d: 'Strong Buy', four_h: 'Buy', moving_averages: 'Strong Buy', oscillators: 'Buy' },
  signals: ['rsi_overbought', 'macd_bullish_cross'],
}

function mockFetch(body: unknown, ok = true) {
  const fetchMock = vi.fn().mockResolvedValue({ ok, json: () => Promise.resolve(body) })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('TechnicalIndicatorsPanel', () => {
  beforeEach(() => _resetIndicatorsCacheForTests())
  afterEach(() => vi.unstubAllGlobals())

  it('stays collapsed and fetches nothing until opened', async () => {
    const fetchMock = mockFetch({ EWZ })
    render(<TechnicalIndicatorsPanel symbol="EWZ" assetKind="etf" />)

    expect(screen.queryByText('RSI')).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Show technical indicators for $EWZ' }))

    expect(await screen.findByText('72 overbought · 4H 64')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/research/indicators?symbols=EWZ&asset_kind=etf')
    expect(screen.getByText('Above signal (crossed)')).toHaveClass('text-emerald-600')
    expect(screen.getByText('+6.3%')).toBeInTheDocument()
    expect(screen.getByText('-1.5%')).toHaveClass('text-rose-600')
    expect(screen.getByText('Golden cross')).toBeInTheDocument()
    expect(screen.getByText('2.4% / day')).toBeInTheDocument()
    expect(screen.getByText('31 strong ↑')).toBeInTheDocument()
    expect(screen.getByText('1.58× avg')).toBeInTheDocument()
    expect(screen.queryByText(/TradingView was unavailable/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Hide technical indicators for $EWZ' }))
    expect(screen.queryByText('RSI')).not.toBeInTheDocument()
  })

  it('notes the computed fallback and skips missing values', async () => {
    mockFetch({
      XYZ: {
        ...EWZ,
        symbol: 'XYZ',
        source: 'price_history',
        rsi: { value: 45, state: 'neutral', four_h: null },
        moving_averages: {
          ...EWZ.moving_averages,
          sma200: null,
          price_vs_sma200_percent: null,
          sma50_vs_sma200: null,
        },
      },
    })
    render(<TechnicalIndicatorsPanel symbol="XYZ" assetKind="stock" />)
    fireEvent.click(screen.getByRole('button'))

    expect(await screen.findByText('45')).toBeInTheDocument()
    expect(screen.queryByText('vs 200D')).not.toBeInTheDocument()
    expect(screen.queryByText('50/200')).not.toBeInTheDocument()
    expect(screen.getByText(/TradingView was unavailable/)).toBeInTheDocument()
  })

  it('says so when there is no data', async () => {
    mockFetch({ NOPE: null })
    render(<TechnicalIndicatorsPanel symbol="NOPE" assetKind="stock" />)
    fireEvent.click(screen.getByRole('button'))

    expect(await screen.findByText('No indicator data for $NOPE.')).toBeInTheDocument()
  })

  it('maps tweet asset kinds to the API kinds', () => {
    expect(indicatorsKind('EQUITY')).toBe('stock')
    expect(indicatorsKind('etf')).toBe('etf')
    expect(indicatorsKind('CRYPTO')).toBe('crypto')
    expect(indicatorsKind('FOREX')).toBeNull()
    expect(indicatorsKind(null)).toBeNull()
  })
})
