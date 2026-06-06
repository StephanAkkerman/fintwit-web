import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import SignaSignal from '../components/SignaSignal'

describe('SignaSignal', () => {
  it('renders nothing when no signal is provided', () => {
    const { container } = render(<SignaSignal signal={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the verdict, score out of 100, confidence and timeframe', () => {
    render(
      <SignaSignal
        signal={{
          source: 'signa',
          symbol: 'AAPL',
          signal: 'Bullish',
          score: 74,
          confidence: 0.81,
          timeframe: '1d',
        }}
      />
    )

    expect(screen.getByText('Signa')).toBeInTheDocument()
    expect(screen.getByText('Bullish')).toBeInTheDocument()
    expect(screen.getByText(/74\/100/)).toBeInTheDocument()
    expect(screen.getByText(/81%/)).toBeInTheDocument()
    // Timeframe is upper-cased for display.
    expect(screen.getByText('1D')).toBeInTheDocument()
  })

  it('omits the timeframe chip when no timeframe is provided', () => {
    render(<SignaSignal signal={{ signal: 'Bullish', score: 50 }} />)
    expect(screen.queryByText('1D')).not.toBeInTheDocument()
    expect(screen.getByText(/50\/100/)).toBeInTheDocument()
  })

  it('color-codes a bullish verdict green', () => {
    render(<SignaSignal signal={{ signal: 'Bullish' }} />)
    expect(screen.getByText('Bullish').className).toContain('emerald')
  })

  it('color-codes a bearish verdict red', () => {
    render(<SignaSignal signal={{ signal: 'Bearish' }} />)
    expect(screen.getByText('Bearish').className).toContain('rose')
  })
})
