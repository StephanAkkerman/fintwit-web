import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { PortfolioTickerBadge } from './PortfolioTickerBadge'

describe('PortfolioTickerBadge', () => {
  it('renders nothing when status is null', () => {
    const { container } = render(<PortfolioTickerBadge status={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the held badge for "active"', () => {
    render(<PortfolioTickerBadge status="active" />)
    const badge = screen.getByLabelText('Currently in your portfolio')
    expect(badge.textContent).toBe('💼')
  })

  it('renders the recently-held badge for "recent"', () => {
    render(<PortfolioTickerBadge status="recent" />)
    const badge = screen.getByLabelText('Recently in your portfolio')
    expect(badge.textContent).toBe('🕓')
  })
})
