import type { FlowBias, ScoredFlowTrade, WeinsteinStage } from '../types'

export const UP = 'text-emerald-600 dark:text-emerald-400'
export const DOWN = 'text-rose-600 dark:text-rose-400'
export const MUTED = 'text-zinc-500 dark:text-zinc-400'

export const BADGE_BASE = 'rounded-full px-2 py-0.5 text-[11px] font-semibold'

const BADGE_TONE = {
  green: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  red: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  sky: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300',
  zinc: 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300',
} as const

/** Premium in dollars as $850K / $1.2M. */
export function fmtMoney(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const abs = Math.abs(value)
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(1)}B`
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(1)}M`
  if (abs >= 1e3) return `$${(value / 1e3).toFixed(0)}K`
  return `$${value.toFixed(0)}`
}

export function fmtSigned(value: number | null | undefined, digits = 1, suffix = '%'): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}${suffix}`
}

export function signTone(value: number | null | undefined): string {
  if (value == null || value === 0) return ''
  return value > 0 ? UP : DOWN
}

export function biasBadge(bias: FlowBias): { label: string; className: string } {
  if (bias === 'bullish') return { label: 'Bullish flow', className: BADGE_TONE.green }
  if (bias === 'bearish') return { label: 'Bearish flow', className: BADGE_TONE.red }
  if (bias === 'mixed') return { label: 'Mixed flow', className: BADGE_TONE.zinc }
  return { label: 'No notable flow', className: BADGE_TONE.zinc }
}

const STAGE_TONE: Record<WeinsteinStage['stage'], keyof typeof BADGE_TONE> = {
  1: 'sky',
  2: 'green',
  3: 'amber',
  4: 'red',
}

export function stageBadge(stage: WeinsteinStage): { label: string; className: string } {
  const name = stage.name.charAt(0).toUpperCase() + stage.name.slice(1)
  return { label: `Stage ${stage.stage} · ${name}`, className: BADGE_TONE[STAGE_TONE[stage.stage]] }
}

/** "NVDA 212.5C Nov 20" for one trade. */
export function contractLabel(trade: Pick<ScoredFlowTrade, 'symbol' | 'option_type' | 'strike' | 'expiry'>): string {
  const side = trade.option_type ? trade.option_type.charAt(0).toUpperCase() : ''
  let expiry = trade.expiry ?? ''
  const parsed = trade.expiry ? new Date(`${trade.expiry}T00:00:00`) : null
  if (parsed && !Number.isNaN(parsed.getTime())) {
    expiry = parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  }
  return `${trade.symbol} ${trade.strike ?? ''}${side} ${expiry}`.trim()
}
