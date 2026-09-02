/**
 * Squarified treemap layout (Bruls, Huizing & van Wijk).
 *
 * Lays out items as nested rectangles whose area is proportional to `value`,
 * keeping row aspect ratios close to square so cells stay readable instead of
 * degenerating into thin slivers. Coordinates are in the same units as the
 * `w`/`h` passed in (percentages or pixels both work).
 */

export type TreemapNode<T> = {
  value: number;
  data: T;
};

export type TreemapRect<T> = {
  x: number;
  y: number;
  w: number;
  h: number;
  value: number;
  data: T;
};

function worstAspect(areas: number[], side: number): number {
  const sum = areas.reduce((a, b) => a + b, 0);
  const max = Math.max(...areas);
  const min = Math.min(...areas);
  const sideSq = side * side;
  const sumSq = sum * sum;
  return Math.max((sideSq * max) / sumSq, sumSq / (sideSq * min));
}

export function squarify<T>(
  nodes: TreemapNode<T>[],
  x: number,
  y: number,
  w: number,
  h: number,
): TreemapRect<T>[] {
  const items = nodes.filter((n) => Number.isFinite(n.value) && n.value > 0);
  if (items.length === 0 || w <= 0 || h <= 0) return [];

  const total = items.reduce((s, n) => s + n.value, 0);
  if (total <= 0) return [];

  const area = w * h;
  const scaled = items
    .map((n) => ({ value: n.value, data: n.data, area: (n.value / total) * area }))
    .sort((a, b) => b.area - a.area);

  const out: TreemapRect<T>[] = [];
  let remaining = scaled;
  let cx = x;
  let cy = y;
  let cw = w;
  let ch = h;

  while (remaining.length > 0) {
    const side = Math.min(cw, ch);
    let row = [remaining[0]];
    let bestWorst = worstAspect([remaining[0].area], side);
    let idx = 1;

    while (idx < remaining.length) {
      const candidateRow = [...row, remaining[idx]];
      const candidateWorst = worstAspect(
        candidateRow.map((r) => r.area),
        side,
      );
      if (candidateWorst > bestWorst) break;
      row = candidateRow;
      bestWorst = candidateWorst;
      idx++;
    }

    const rowArea = row.reduce((s, r) => s + r.area, 0);
    const rowThickness = rowArea / side;
    let offset = 0;

    if (cw >= ch) {
      // Row runs down the left edge; thickness eats into the width.
      for (const item of row) {
        const length = item.area / rowThickness;
        out.push({ x: cx, y: cy + offset, w: rowThickness, h: length, value: item.value, data: item.data });
        offset += length;
      }
      cx += rowThickness;
      cw -= rowThickness;
    } else {
      // Row runs along the top edge; thickness eats into the height.
      for (const item of row) {
        const length = item.area / rowThickness;
        out.push({ x: cx + offset, y: cy, w: length, h: rowThickness, value: item.value, data: item.data });
        offset += length;
      }
      cy += rowThickness;
      ch -= rowThickness;
    }

    remaining = remaining.slice(row.length);
  }

  return out;
}
