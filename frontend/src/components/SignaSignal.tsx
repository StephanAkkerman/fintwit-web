import type { AssetSignaSignal } from '../types'
import { directionTextClass } from '../utils/directionColor'

export default function SignaSignal({
  signal,
  className = '',
}: {
  signal?: AssetSignaSignal | null
  className?: string
}) {
  if (!signal || !signal.signal) {
    return null
  }

  const colorClass = directionTextClass(signal.signal)

  const stats: string[] = []
  if (typeof signal.score === 'number') {
    stats.push(`score ${Math.round(signal.score)}`)
  }
  if (typeof signal.confidence === 'number') {
    stats.push(`${Math.round(signal.confidence * 100)}% conf`)
  }

  return (
    <div className={`grid gap-1.5 ${className}`.trim()}>
      <div className="flex items-center justify-between gap-2 rounded-lg bg-zinc-100 px-2 py-1 text-[10px] text-zinc-700 dark:bg-zinc-800/70 dark:text-zinc-200">
        <div className="flex min-w-0 items-center gap-1.5">
          <span className="shrink-0 rounded-full bg-zinc-200 px-1.5 py-0.5 font-semibold uppercase tracking-wide text-[9px] text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300">
            Signa
          </span>
          <span className={`truncate font-semibold ${colorClass}`}>{signal.signal}</span>
        </div>
        {stats.length > 0 && (
          <span className="shrink-0 text-zinc-500 dark:text-zinc-400">{stats.join(' · ')}</span>
        )}
      </div>
    </div>
  )
}
