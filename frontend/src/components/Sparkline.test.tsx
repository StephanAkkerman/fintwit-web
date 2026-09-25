import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Sparkline } from './Sparkline'

const UP_COLOR = '#34d399'
const DOWN_COLOR = '#fb7185'

describe('Sparkline', () => {
  it('renders nothing for fewer than two points', () => {
    const { container } = render(<Sparkline data={[1]} />)
    expect(container.querySelector('svg')).toBeNull()
  })

  it('colors the line by its own first-to-last movement, not just its highest point', () => {
    // Rises then falls below the start: an overall decline even though the
    // series spends most of its time above where it started.
    const { container } = render(<Sparkline data={[100, 110, 105, 95]} />)
    const polyline = container.querySelector('polyline')
    expect(polyline).toHaveAttribute('stroke', DOWN_COLOR)
  })

  it('colors the line green when it ends above where it started', () => {
    const { container } = render(<Sparkline data={[100, 95, 90, 105]} />)
    const polyline = container.querySelector('polyline')
    expect(polyline).toHaveAttribute('stroke', UP_COLOR)
  })

  it('draws the end-point marker in the same color as the line', () => {
    const { container } = render(<Sparkline data={[100, 90]} />)
    const polyline = container.querySelector('polyline')
    const circle = container.querySelector('circle')
    expect(circle).toHaveAttribute('fill', polyline?.getAttribute('stroke'))
  })

  it('respects a custom width and height', () => {
    const { container } = render(<Sparkline data={[1, 2]} width={64} height={24} />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveAttribute('width', '64')
    expect(svg).toHaveAttribute('height', '24')
  })
})
