import type { AssetKind, TrendSummary, TrendTicker, TrendWindow } from '../types'

export const TREND_WINDOWS: TrendWindow[] = ['1d', '7d', '30d']

export const TREND_WINDOW_LABEL: Record<TrendWindow, string> = {
  '1d': 'past 24 hours',
  '7d': 'past 7 days',
  '30d': 'past 30 days',
}

// Chart ink, matching the dashboard's Tailwind zinc/emerald/rose classes.
export const INK = {
  text: '#f4f4f5',     // zinc-100
  muted: '#71717a',    // zinc-500
  grid: '#27272a',     // zinc-800
  card: '#18181b',     // zinc-900
  empty: '#27272a',
  bull: '#34d399',     // emerald-400
  bear: '#fb7185',     // rose-400
  neutral: '#52525b',  // zinc-600
  accent: '#38bdf8',   // sky-400
  violet: '#a78bfa',   // violet-400
} as const

// Categorical slots for per-ticker lines, validated for a dark surface.
export const SERIES_COLORS = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#2f9a2f', '#9085e9', '#e66767']

/** Mention growth vs the previous window; Infinity for a ticker that is new this window. */
export function growth(t: Pick<TrendTicker, 'mentions' | 'previous_mentions'>): number {
  if (t.previous_mentions === 0) return t.mentions > 0 ? Infinity : 1
  return t.mentions / t.previous_mentions
}

export function netOf(bull: number, bear: number): number | null {
  return bull + bear === 0 ? null : (bull - bear) / (bull + bear)
}

/** Net sentiment over the first and second half of the window. */
export function halves(t: TrendTicker): { first: number | null; last: number | null; firstN: number; lastN: number } {
  const n = t.series.bull.length
  const mid = Math.floor(n / 2)
  const sum = (a: number[], from: number, to: number) => a.slice(from, to).reduce((x, y) => x + y, 0)
  const b1 = sum(t.series.bull, 0, mid), e1 = sum(t.series.bear, 0, mid)
  const b2 = sum(t.series.bull, mid, n), e2 = sum(t.series.bear, mid, n)
  return { first: netOf(b1, e1), last: netOf(b2, e2), firstN: b1 + e1, lastN: b2 + e2 }
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)) as [number, number, number]
}

function mix(a: string, b: string, t: number): string {
  const A = hexToRgb(a), B = hexToRgb(b)
  return `rgb(${A.map((v, i) => Math.round(v + (B[i] - v) * t)).join(',')})`
}

/** Diverging bear → neutral → bull colour; saturates at ±0.6. */
export function sentimentColor(net: number | null): string {
  const v = net ?? 0
  const k = Math.min(1, Math.abs(v) / 0.6)
  return v >= 0 ? mix(INK.neutral, INK.bull, k) : mix(INK.neutral, INK.bear, k)
}

/**
 * A stable colour per ticker: the colour follows the entity, not its rank, so
 * a ticker keeps its colour when the lines reorder. Each ticker starts at a
 * slot picked from its name and takes the next free one on a clash.
 */
export function assignSeriesColors(tickers: string[]): Record<string, string> {
  const taken = new Set<number>()
  const out: Record<string, string> = {}
  for (const t of [...tickers].sort()) {
    let h = 0
    for (const c of t) h = (h * 31 + c.charCodeAt(0)) >>> 0
    let slot = h % SERIES_COLORS.length
    for (let k = 0; k < SERIES_COLORS.length && taken.has(slot); k++) slot = (slot + 1) % SERIES_COLORS.length
    taken.add(slot)
    out[t] = SERIES_COLORS[slot]
  }
  return out
}

/**
 * Mention rank of each ticker in every bucket, ranked on a trailing sum of
 * `smooth` buckets so a single noisy hour doesn't reshuffle the chart.
 */
export function ranksOverTime(tickers: TrendTicker[], smooth: number): Map<string, number[]> {
  const n = tickers[0]?.series.mentions.length ?? 0
  const trailing = new Map(tickers.map(t => {
    const m = t.series.mentions
    return [t.ticker, m.map((_, i) => {
      let s = 0
      for (let k = Math.max(0, i - smooth + 1); k <= i; k++) s += m[k]
      return s
    })]
  }))
  const out = new Map<string, number[]>(tickers.map(t => [t.ticker, []]))
  for (let i = 0; i < n; i++) {
    const order = [...tickers].sort((a, b) =>
      trailing.get(b.ticker)![i] - trailing.get(a.ticker)![i] || a.ticker.localeCompare(b.ticker))
    order.forEach((t, k) => out.get(t.ticker)!.push(k + 1))
  }
  return out
}

export function smoothingFor(bucketCount: number): number {
  return Math.max(3, Math.round(bucketCount / 5))
}

export function formatBucket(iso: string, win: TrendWindow, long = false): string {
  const d = new Date(iso)
  if (win === '1d') return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  if (win === '7d') {
    return long
      ? d.toLocaleDateString('en-GB', { weekday: 'short', hour: '2-digit', minute: '2-digit' })
      : d.toLocaleDateString('en-GB', { weekday: 'short' })
  }
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

export const fmtCount = (n: number) => (n >= 10000 ? `${(n / 1000).toFixed(1)}k` : n.toLocaleString('en-US'))

export function fmtNet(n: number | null): string {
  if (n === null) return '–'
  const sign = n > 0.005 ? '+' : n < -0.005 ? '−' : ''
  return `${sign}${Math.abs(n).toFixed(2)}`
}

export const fmtPct = (p: number) => `${p >= 0 ? '+' : '−'}${Math.abs(p * 100).toFixed(1)}%`

export function fmtPrice(p: number): string {
  if (p >= 1000) return `$${Math.round(p).toLocaleString('en-US')}`
  if (p >= 10) return `$${p.toFixed(2)}`
  if (p >= 1) return `$${p.toFixed(3)}`
  return `$${p.toPrecision(3)}`
}

export function fmtGrowth(g: number): string {
  if (!Number.isFinite(g)) return 'new'
  return `×${g >= 10 ? g.toFixed(0) : g.toFixed(1)}`
}

/** First and last quoted price in the window, when at least two buckets carried one. */
export function priceChange(t: TrendTicker): { first: number; last: number; change: number } | null {
  const pts = t.series.price.filter((p): p is number => p !== null && p > 0)
  if (pts.length < 2) return null
  const first = pts[0], last = pts[pts.length - 1]
  return { first, last, change: last / first - 1 }
}

// ── Headline ────────────────────────────────────────────────────────────

/** A run of headline text: plain words, a clickable ticker, or a figure. */
export type Segment = string | { ticker: string } | { value: string }

export type Tone = 'bull' | 'bear' | 'accent' | 'muted' | 'violet'

export interface HeadlineItem { tone: Tone; segments: Segment[] }

export interface Headline { lead: Segment[]; items: HeadlineItem[] }

/**
 * The rule-based "what happened" summary above the charts.
 *
 * Only tickers with a meaningful share of the chatter qualify (at least 3
 * mentions and 3% of the leader), so a ticker going from 1 to 4 mentions
 * never headlines. Each rule is skipped when nothing qualifies.
 */
export function buildHeadline(data: TrendSummary, assetKind: AssetKind): Headline {
  const label = TREND_WINDOW_LABEL[data.window]
  const ts = data.tickers
  if (ts.length === 0) {
    return { lead: [`No ticker mentions in the ${label} yet.`], items: [] }
  }
  const leader = ts[0]
  const floor = Math.max(3, 0.03 * leader.mentions)
  const eligible = ts.filter(t => t.mentions >= floor)

  const mover = [...eligible].sort((a, b) => growth(b) - growth(a) || b.mentions - a.mentions)[0]
  const moverRising = mover && growth(mover) >= 1.5

  const flips = eligible
    .map(t => ({ t, h: halves(t) }))
    .filter(({ h }) => h.first !== null && h.last !== null && h.firstN >= 3 && h.lastN >= 3)
    .map(({ t, h }) => ({ t, first: h.first!, last: h.last!, delta: h.last! - h.first! }))
    .filter(f => Math.abs(f.delta) >= 0.3)
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
  const flip = flips.find(f => f.t !== mover) ?? flips[0]

  const lead: Segment[] = []
  if (moverRising) {
    lead.push({ ticker: mover.ticker },
      Number.isFinite(growth(mover))
        ? ` broke out over the ${label} with ${fmtGrowth(growth(mover))} its previous chatter`
        : ` appeared out of nowhere over the ${label} with ${mover.mentions} mentions`)
  } else {
    lead.push({ ticker: leader.ticker }, ` led the ${label} with ${fmtCount(leader.mentions)} mentions`)
  }
  if (flip && flip.t.ticker !== (moverRising ? mover.ticker : leader.ticker)) {
    lead.push(', while ', { ticker: flip.t.ticker }, ` turned ${flip.delta < 0 ? 'bearish' : 'bullish'}.`)
  } else {
    lead.push('.')
  }

  const items: HeadlineItem[] = []
  if (moverRising) {
    const pc = priceChange(mover)
    items.push({
      tone: 'bull',
      segments: [
        { ticker: mover.ticker }, ' mentions went from ', { value: fmtCount(mover.previous_mentions) },
        ' to ', { value: fmtCount(mover.mentions) }, '. Net sentiment is ', { value: fmtNet(mover.net_sentiment) },
        ...(pc ? [' and the price moved ', { value: fmtPct(pc.change) }] : []), '.',
      ],
    })
  }
  if (flip) {
    items.push({
      tone: flip.delta < 0 ? 'bear' : 'bull',
      segments: [{ ticker: flip.t.ticker }, ' sentiment went from ', { value: fmtNet(flip.first) }, ' to ', { value: fmtNet(flip.last) }, ' during the window.'],
    })
  }
  const entrants = ts.slice(0, 10).filter(t =>
    (t.previous_rank === null || t.previous_rank > 10) && t.mentions >= floor && !(moverRising && t === mover))
  if (entrants.length) {
    const segs: Segment[] = ['New in the top 10: ']
    entrants.slice(0, 4).forEach((t, i) => { if (i) segs.push(', '); segs.push({ ticker: t.ticker }) })
    segs.push('.')
    items.push({ tone: 'accent', segments: segs })
  }
  const cooling = ts
    .filter(t => t.previous_mentions >= floor && growth(t) < 0.8)
    .sort((a, b) => growth(a) - growth(b))[0]
  if (cooling) {
    items.push({
      tone: 'muted',
      segments: ['Cooling off: ', { ticker: cooling.ticker }, ' is down to ', { value: `${Math.round(growth(cooling) * 100)}%` }, ' of its previous volume.'],
    })
  }
  if (assetKind === 'all') {
    const share = (k: Record<string, number>) => {
      const total = k.EQUITY + k.CRYPTO + k.FOREX
      return total ? k.CRYPTO / total : null
    }
    const now = share(data.kind_share.current), prev = share(data.kind_share.previous)
    if (now !== null && prev !== null && Math.abs(now - prev) >= 0.02) {
      items.push({
        tone: 'violet',
        segments: ["Crypto's share of all mentions went from ", { value: `${Math.round(prev * 100)}%` }, ' to ', { value: `${Math.round(now * 100)}%` }, '.'],
      })
    }
  }
  return { lead, items }
}
