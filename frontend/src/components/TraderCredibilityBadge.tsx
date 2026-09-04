import type { TraderHorizonStat } from '../types'
import { hitRateClass } from '../utils/traderFormat'

interface Props {
  stat: TraderHorizonStat | null | undefined
}

/**
 * Compact "🎯 69%" pill for a tweet author's call accuracy, next to their
 * handle in `TweetCard`. Renders nothing until there's a graded track
 * record (see `MIN_CALLS_FOR_BADGE` server-side) — silence here just means
 * not enough data yet, not that the trader is untracked.
 */
export function TraderCredibilityBadge({ stat }: Props) {
  if (!stat || stat.hit_rate == null) return null

  const pct = Math.round(stat.hit_rate * 100)
  const title = `${pct}% hit rate over ${stat.graded_calls} calls, graded ${stat.horizon_days}d after each tweet`

  return (
    <span
      title={title}
      aria-label={title}
      className={`inline-flex shrink-0 items-center gap-0.5 rounded-full bg-zinc-100 px-1.5 py-0.5 text-[10px] font-bold tabular-nums dark:bg-zinc-800 ${hitRateClass(stat.hit_rate)}`}
    >
      🎯 {pct}%
    </span>
  )
}
