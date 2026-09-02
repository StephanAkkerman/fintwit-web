import { describe, expect, it } from 'vitest'
import { squarify } from '../utils/treemap'

describe('squarify', () => {
  it('returns one rect filling the container for a single item', () => {
    const rects = squarify([{ value: 10, data: 'a' }], 0, 0, 200, 100)
    expect(rects).toHaveLength(1)
    expect(rects[0]).toMatchObject({ x: 0, y: 0, w: 200, h: 100 })
  })

  it('conserves total area and stays within container bounds', () => {
    const nodes = [5, 3, 2, 8, 1, 13, 4].map((value, i) => ({ value, data: i }))
    const rects = squarify(nodes, 0, 0, 300, 150)

    expect(rects).toHaveLength(nodes.length)

    const totalArea = rects.reduce((sum, r) => sum + r.w * r.h, 0)
    expect(totalArea).toBeCloseTo(300 * 150, 0)

    for (const r of rects) {
      expect(r.x).toBeGreaterThanOrEqual(-1e-6)
      expect(r.y).toBeGreaterThanOrEqual(-1e-6)
      expect(r.x + r.w).toBeLessThanOrEqual(300 + 1e-6)
      expect(r.y + r.h).toBeLessThanOrEqual(150 + 1e-6)
      expect(r.w).toBeGreaterThan(0)
      expect(r.h).toBeGreaterThan(0)
    }
  })

  it('offsets the layout to a non-zero origin', () => {
    const rects = squarify(
      [
        { value: 1, data: 'a' },
        { value: 1, data: 'b' },
      ],
      50,
      20,
      100,
      100,
    )
    for (const r of rects) {
      expect(r.x).toBeGreaterThanOrEqual(50 - 1e-6)
      expect(r.y).toBeGreaterThanOrEqual(20 - 1e-6)
      expect(r.x + r.w).toBeLessThanOrEqual(150 + 1e-6)
      expect(r.y + r.h).toBeLessThanOrEqual(120 + 1e-6)
    }
  })

  it('ignores zero and negative values, and empty input', () => {
    expect(squarify([], 0, 0, 100, 100)).toEqual([])
    expect(
      squarify(
        [
          { value: 0, data: 'a' },
          { value: -1, data: 'b' },
        ],
        0,
        0,
        100,
        100,
      ),
    ).toEqual([])
  })

  it('handles a zero-size container without crashing', () => {
    expect(squarify([{ value: 1, data: 'a' }], 0, 0, 0, 0)).toEqual([])
  })
})
