import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import StocktwitsSentiment from '../components/StocktwitsSentiment'

describe('StocktwitsSentiment', () => {
  it('renders nothing when no sentiment is provided', () => {
    const { container } = render(<StocktwitsSentiment sentiment={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when bullish_percent is missing', () => {
    const { container } = render(<StocktwitsSentiment sentiment={{ bearish_percent: 40 }} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the bullish/bearish split', () => {
    render(<StocktwitsSentiment sentiment={{ bullish_percent: 62.5, bearish_percent: 37.5 }} />)

    expect(screen.getByText('StockTwits')).toBeInTheDocument()
    expect(screen.getByText('Bullish')).toBeInTheDocument()
    expect(screen.getByText('63% / 38%')).toBeInTheDocument()
  })

  it('derives the bearish share when only bullish_percent is provided', () => {
    render(<StocktwitsSentiment sentiment={{ bullish_percent: 70 }} />)
    expect(screen.getByText('70% / 30%')).toBeInTheDocument()
  })

  it('color-codes a bullish split green', () => {
    render(<StocktwitsSentiment sentiment={{ bullish_percent: 60, bearish_percent: 40 }} />)
    expect(screen.getByText('Bullish').className).toContain('emerald')
  })

  it('color-codes a bearish split red', () => {
    render(<StocktwitsSentiment sentiment={{ bullish_percent: 30, bearish_percent: 70 }} />)
    expect(screen.getByText('Bearish').className).toContain('rose')
  })
})
