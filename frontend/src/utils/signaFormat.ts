import { classifyDirection } from './directionColor'

/** Arrow glyph for a direction/verdict: ▲ bullish, ▼ bearish, ◆ neutral. */
export function directionArrow(direction: string | null | undefined): string {
  const kind = classifyDirection(direction)
  if (kind === 'bullish') return '▲'
  if (kind === 'bearish') return '▼'
  return '◆'
}

/** Tailwind chip classes for a Signa letter grade (A/B/C/…). */
export function gradeClasses(grade: string | null | undefined): string {
  switch ((grade ?? '').toUpperCase()) {
    case 'A':
      return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300'
    case 'B':
      return 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300'
    case 'C':
      return 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300'
    default:
      return 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300'
  }
}

/** "5m ago" / "2h ago" / "3d ago" relative time, or '' when unparseable. */
export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const diffMs = Date.now() - then
  const mins = Math.round(diffMs / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return `${days}d ago`
}

/** "Jun 5, 3:04 PM" absolute time, or '' when unparseable. */
export function absoluteTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}
