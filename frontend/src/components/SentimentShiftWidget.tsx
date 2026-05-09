import type { AssetKind, SentimentLabel } from '../types'
import { useSentimentShift } from '../hooks/useSentimentShift'

interface BadgeProps {
  label: SentimentLabel
}

function Badge({ label }: BadgeProps) {
  const styles: Record<SentimentLabel, string> = {
    BULL: 'bg-emerald-950 text-emerald-400',
    BEAR: 'bg-rose-950 text-rose-400',
    NEUTRAL: 'bg-zinc-800 text-zinc-400',
  }
  return (
    <span className={`${styles[label]} text-xs font-medium px-1.5 py-0.5 rounded`}>
      {label}
    </span>
  )
}

interface Props {
  assetKind: AssetKind
}

export function SentimentShiftWidget({ assetKind }: Props) {
  const { data, loading, error } = useSentimentShift(assetKind)

  if (loading) {
    return (
      <div className="bg-zinc-900 rounded-2xl p-4 flex flex-col gap-3">
        <div className="h-4 w-32 bg-zinc-800 rounded animate-pulse" />
        {[0, 1, 2].map(i => (
          <div key={i} className="h-5 bg-zinc-800 rounded animate-pulse" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-zinc-900 rounded-2xl p-4 text-zinc-500 text-sm">
        Failed to load sentiment data.
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="bg-zinc-900 rounded-2xl p-4 text-zinc-500 text-sm">
        No sentiment shift data.
      </div>
    )
  }

  const visible = data.slice(0, 10)
  const overflow = data.length - 10

  return (
    <div className="bg-zinc-900 rounded-2xl p-4 flex flex-col gap-3">
      <h2 className="text-zinc-100 text-sm font-semibold">Sentiment Shift</h2>
      {visible.map(item => (
        <div key={item.ticker} className="flex items-center justify-between">
          <span className="text-zinc-100 text-sm font-mono">{item.ticker}</span>
          <span className="flex items-center gap-1.5">
            <Badge label={item.sentiment_label_prev} />
            <span className="text-zinc-500 text-xs">→</span>
            <Badge label={item.sentiment_label_24h} />
          </span>
        </div>
      ))}
      {overflow > 0 && (
        <p className="text-zinc-500 text-xs">+{overflow} more</p>
      )}
    </div>
  )
}
