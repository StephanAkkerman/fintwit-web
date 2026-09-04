import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { TraderCredibilityBadge } from './TraderCredibilityBadge'
import type { TraderHorizonStat } from '../types'

function stat(overrides: Partial<TraderHorizonStat> = {}): TraderHorizonStat {
  return {
    horizon_days: 7,
    graded_calls: 10,
    correct_calls: 7,
    hit_rate: 0.7,
    avg_return_pct: 4.2,
    ...overrides,
  }
}

describe('TraderCredibilityBadge', () => {
  it('renders nothing when stat is undefined', () => {
    const { container } = render(<TraderCredibilityBadge stat={undefined} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when stat is null', () => {
    const { container } = render(<TraderCredibilityBadge stat={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when hit_rate is null', () => {
    const { container } = render(<TraderCredibilityBadge stat={stat({ hit_rate: null })} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the rounded hit rate percentage', () => {
    render(<TraderCredibilityBadge stat={stat({ hit_rate: 0.694 })} />)
    expect(screen.getByText('🎯 69%')).toBeInTheDocument()
  })

  it('includes the sample size and horizon in the title', () => {
    render(<TraderCredibilityBadge stat={stat({ graded_calls: 12, horizon_days: 30 })} />)
    const badge = screen.getByLabelText(/12 calls, graded 30d after each tweet/)
    expect(badge).toBeInTheDocument()
  })
})
