/** Tailwind text-color classes for a hit-rate (0-1), shared by the leaderboard and the tweet-card badge. */
export function hitRateClass(hitRate: number): string {
  if (hitRate >= 0.6) return 'text-emerald-600 dark:text-emerald-400'
  if (hitRate <= 0.4) return 'text-rose-600 dark:text-rose-400'
  return 'text-zinc-600 dark:text-zinc-300'
}

/** Tailwind text-color classes for a signed average-return percentage. */
export function returnClass(value: number | null): string {
  if (value == null) return 'text-zinc-400 dark:text-zinc-500'
  if (value > 0) return 'text-emerald-600 dark:text-emerald-400'
  if (value < 0) return 'text-rose-600 dark:text-rose-400'
  return 'text-zinc-500 dark:text-zinc-400'
}

/** "+4.8%" / "-6.1%" / "—" for a signed average-return percentage. */
export function formatReturnPct(value: number | null): string {
  if (value == null) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}
