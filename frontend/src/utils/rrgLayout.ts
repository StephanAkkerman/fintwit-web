/**
 * Layout helpers for the Relative Rotation Graph (RRG) in `SectorRotationWidget`.
 *
 * Kept free of React/Recharts so the geometry can be unit-tested directly.
 */

export type LabelAnchor = {
  id: string
  /** Head dot centre, in pixels. */
  x: number
  y: number
  text: string
}

export type PlacedLabel = {
  id: string
  /** Top-left of the label box, in pixels. */
  x: number
  y: number
  width: number
  height: number
  /** True when the label had to move away from its dot; draw a leader line. */
  displaced: boolean
}

type Box = { x: number; y: number; width: number; height: number }

type Bounds = { x: number; y: number; width: number; height: number }

const CHAR_WIDTH = 6.4
const LABEL_HEIGHT = 12
const DOT_CLEARANCE = 7

function overlapArea(a: Box, b: Box): number {
  const w = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x)
  const h = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y)
  return w > 0 && h > 0 ? w * h : 0
}

function outside(box: Box, bounds: Bounds): number {
  const left = Math.max(0, bounds.x - box.x)
  const right = Math.max(0, box.x + box.width - (bounds.x + bounds.width))
  const top = Math.max(0, bounds.y - box.y)
  const bottom = Math.max(0, box.y + box.height - (bounds.y + bounds.height))
  return (left + right) * box.height + (top + bottom) * box.width
}

/**
 * Greedily place one text label per head dot so labels don't sit on top of
 * each other or on another sector's dot.
 *
 * `obstacles` are extra points to steer clear of (the trails' vertices).
 *
 * Each label tries eight positions around its dot (right first, as a reader
 * expects), then the same eight one step further out. The first position that
 * collides with nothing wins; if every position collides, the least-overlapping
 * one is used, so a label is never dropped.
 */
export function placeLabels(
  anchors: LabelAnchor[],
  bounds: Bounds,
  obstacles: Array<{ x: number; y: number }> = []
): PlacedLabel[] {
  const dots: Box[] = anchors.map((a) => ({
    x: a.x - DOT_CLEARANCE,
    y: a.y - DOT_CLEARANCE,
    width: DOT_CLEARANCE * 2,
    height: DOT_CLEARANCE * 2,
  }))
  // Trail vertices: softer obstacles — covering a tail is worse than nothing,
  // but better than covering another sector's head or label.
  const trail: Box[] = obstacles.map((o) => ({ x: o.x - 3, y: o.y - 3, width: 6, height: 6 }))
  const placed: PlacedLabel[] = []

  // Top-to-bottom, left-to-right: a stable order keeps labels from jumping
  // around between renders with near-identical data.
  const order = anchors
    .map((a, i) => ({ a, i }))
    .sort((p, q) => p.a.y - q.a.y || p.a.x - q.a.x)

  for (const { a, i } of order) {
    const width = a.text.length * CHAR_WIDTH + 2
    const height = LABEL_HEIGHT
    const candidates: Array<Box & { displaced: boolean }> = []
    for (const ring of [0, 1]) {
      const gap = DOT_CLEARANCE + ring * 12
      const displaced = ring > 0
      const midY = a.y - height / 2
      candidates.push(
        { x: a.x + gap, y: midY, width, height, displaced },
        { x: a.x - gap - width, y: midY, width, height, displaced },
        { x: a.x - width / 2, y: a.y - gap - height, width, height, displaced },
        { x: a.x - width / 2, y: a.y + gap, width, height, displaced },
        { x: a.x + gap * 0.7, y: a.y - gap * 0.7 - height, width, height, displaced },
        { x: a.x + gap * 0.7, y: a.y + gap * 0.7, width, height, displaced },
        { x: a.x - gap * 0.7 - width, y: a.y + gap * 0.7, width, height, displaced },
        { x: a.x - gap * 0.7 - width, y: a.y - gap * 0.7 - height, width, height, displaced },
      )
    }

    let best = candidates[0]
    let bestCost = Infinity
    for (const c of candidates) {
      let cost = outside(c, bounds) * 4
      for (const [j, dot] of dots.entries()) if (j !== i) cost += overlapArea(c, dot)
      for (const t of trail) cost += overlapArea(c, t) * 0.5
      for (const p of placed) cost += overlapArea(c, p) * 2
      if (cost < bestCost) {
        best = c
        bestCost = cost
        if (cost === 0) break
      }
    }

    placed.push({ id: a.id, ...best })
  }

  return anchors.map((a) => placed.find((p) => p.id === a.id)!)
}

/**
 * Axis domain fitted to the data but always containing 100 (the RRG's neutral
 * point, where the quadrants meet), rounded out to a "nice" step so the ticks
 * read as 96 / 98 / 100 / 102 rather than 95.02 / 98.02 / 101.02.
 */
export function rrgDomain(values: number[]): { domain: [number, number]; ticks: number[] } {
  const lo = Math.min(100, ...values)
  const hi = Math.max(100, ...values)
  const pad = Math.max((hi - lo) * 0.08, 0.5)
  const span = hi - lo + pad * 2
  const step = [0.5, 1, 2, 2.5, 5, 10].find((s) => span / s <= 7) ?? 10
  const min = Math.floor((lo - pad) / step) * step
  const max = Math.ceil((hi + pad) / step) * step
  const ticks: number[] = []
  for (let t = min; t <= max + 1e-9; t += step) ticks.push(Number(t.toFixed(2)))
  return { domain: [min, max], ticks }
}
