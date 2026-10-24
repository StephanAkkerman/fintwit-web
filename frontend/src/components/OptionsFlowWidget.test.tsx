import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OptionsFlowWidget from './OptionsFlowWidget'
import type { OptionsFlow } from '../types'

vi.mock('../hooks/useResearch', () => ({
  useOptionsFlow: vi.fn(),
}))

import { useOptionsFlow } from '../hooks/useResearch'
const mockUseOptionsFlow = vi.mocked(useOptionsFlow)

const DATA = {
  symbol: null,
  bias: 'bullish',
  scored_bullish_premium: 19_159_380,
  scored_bearish_premium: 9_749_870,
  call_premium: 50_982_966,
  put_premium: 40_005_983,
  top_scored: [
    {
      symbol: 'HWM',
      direction: 'BEARISH',
      conviction: 72,
      option_type: 'PUT',
      strike: 190,
      expiry: '2026-11-20',
      premium: 8_435_610,
      sweep: true,
      rationale: 'Large put buying into earnings',
      at: 'a',
    },
  ],
  top_bullish: [{ symbol: 'MU', scored_bullish_premium: 6_817_025, bias: 'bullish' }],
  top_bearish: [],
  top_call_buying: [{ symbol: 'TSLA', bullish_call_premium: 3_784_110, bias: 'mixed' }],
} as unknown as OptionsFlow

type FlowState = ReturnType<typeof useOptionsFlow>

describe('OptionsFlowWidget', () => {
  beforeEach(() => {
    mockUseOptionsFlow.mockReset()
  })

  it('ranks symbols by premium and lists the biggest scored trades', () => {
    mockUseOptionsFlow.mockReturnValue({ data: DATA, loading: false, error: false, missing: false } as FlowState)
    const onTickerClick = vi.fn()
    render(<OptionsFlowWidget onTickerClick={onTickerClick} />)

    expect(mockUseOptionsFlow).toHaveBeenCalledWith(null)
    expect(screen.getByText('Bullish flow')).toBeInTheDocument()
    expect(screen.getByText('$19.2M')).toHaveClass('text-emerald-600')
    expect(screen.getByText('$6.8M')).toBeInTheDocument()
    expect(screen.getByText('None today.')).toBeInTheDocument()
    expect(screen.getByText('Large put buying into earnings')).toBeInTheDocument()
    expect(screen.getByText(/HWM 190P/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '$TSLA' }))
    expect(onTickerClick).toHaveBeenCalledWith('TSLA')
  })

  it('shows an error when the flow fails', () => {
    mockUseOptionsFlow.mockReturnValue({ data: null, loading: false, error: true, missing: false } as FlowState)
    render(<OptionsFlowWidget />)
    expect(screen.getByText('Could not load options flow.')).toBeInTheDocument()
  })
})
