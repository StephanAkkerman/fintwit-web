export type Direction = 'bullish' | 'bearish' | 'neutral'

const DIRECTION_TEXT_CLASS: Record<Direction, string> = {
  bullish: 'text-emerald-600 dark:text-emerald-400',
  bearish: 'text-rose-600 dark:text-rose-400',
  neutral: 'text-zinc-500 dark:text-zinc-400',
}

/**
 * Map a free-form verdict (e.g. "Bullish", "Strong Buy", "up") to a direction.
 * Shared by the Signa signal and TradingView TA so the color language matches.
 */
export function classifyDirection(value: string | null | undefined): Direction {
  const normalized = (value ?? '').trim().toLowerCase()
  if (!normalized) return 'neutral'
  if (/(bull|buy|\bup\b|\blong\b|positive)/.test(normalized)) return 'bullish'
  if (/(bear|sell|\bdown\b|\bshort\b|negative)/.test(normalized)) return 'bearish'
  return 'neutral'
}

/** Tailwind text-color classes (green / red / grey) for a verdict's direction. */
export function directionTextClass(value: string | null | undefined): string {
  return DIRECTION_TEXT_CLASS[classifyDirection(value)]
}
