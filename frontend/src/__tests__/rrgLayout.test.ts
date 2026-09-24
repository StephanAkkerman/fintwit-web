import { describe, expect, it } from 'vitest'
import { placeLabels, rrgDomain } from '../utils/rrgLayout'

const bounds = { x: 0, y: 0, width: 400, height: 300 }

function overlaps(a: { x: number; y: number; width: number; height: number }, b: typeof a) {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height
}

describe('placeLabels', () => {
  it('puts a lone label to the right of its dot', () => {
    const [label] = placeLabels([{ id: 'XLK', text: 'XLK', x: 100, y: 100 }], bounds)
    expect(label.x).toBeGreaterThan(100)
    expect(label.displaced).toBe(false)
  })

  it('keeps labels of near-coincident dots from overlapping', () => {
    const anchors = [
      { id: 'XLU', text: 'XLU', x: 200, y: 150 },
      { id: 'XLE', text: 'XLE', x: 203, y: 154 },
      { id: 'XLRE', text: 'XLRE', x: 210, y: 146 },
    ]
    const labels = placeLabels(anchors, bounds)
    expect(labels.map((l) => l.id)).toEqual(['XLU', 'XLE', 'XLRE'])
    for (let i = 0; i < labels.length; i++) {
      for (let j = i + 1; j < labels.length; j++) {
        expect(overlaps(labels[i], labels[j])).toBe(false)
      }
    }
  })

  it('flips a label inward at the right edge of the plot', () => {
    const [label] = placeLabels([{ id: 'XLK', text: 'XLK', x: 398, y: 100 }], bounds)
    expect(label.x + label.width).toBeLessThanOrEqual(400)
  })
})

describe('rrgDomain', () => {
  it('always contains 100 and uses round ticks', () => {
    const { domain, ticks } = rrgDomain([101.3, 104.9, 102.2])
    expect(domain[0]).toBeLessThanOrEqual(100)
    expect(domain[1]).toBeGreaterThanOrEqual(104.9)
    expect(ticks).toContain(100)
    for (const t of ticks) expect(Number.isInteger(t * 2)).toBe(true)
  })

  it('handles an empty input', () => {
    const { domain } = rrgDomain([])
    expect(domain[0]).toBeLessThan(100)
    expect(domain[1]).toBeGreaterThan(100)
  })
})
