import type { RedditSubredditSummary, RedditTrendReport } from '../types'

interface Props {
  data: RedditTrendReport
}

function moodTone(mood: string | null | undefined): string {
  if (mood === 'bullish') return 'text-emerald-400'
  if (mood === 'bearish') return 'text-rose-400'
  return 'text-zinc-300'
}

function formatSigned(value: number | null | undefined): string {
  const v = value ?? 0
  return (v >= 0 ? '+' : '') + v.toFixed(2)
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl bg-zinc-950/60 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="font-mono text-sm font-semibold tabular-nums text-zinc-100">{value}</div>
    </div>
  )
}

// Share of bullish / neutral / bearish posts as one stacked bar: the mood
// label alone hides whether "neutral" means calm or evenly split.
function SentimentBar({ breakdown }: { breakdown: Record<string, number> }) {
  const bullish = breakdown.bullish ?? 0
  const neutral = breakdown.neutral ?? 0
  const bearish = breakdown.bearish ?? 0
  const total = bullish + neutral + bearish
  if (total === 0) return null
  const pct = (n: number) => `${((n / total) * 100).toFixed(0)}%`

  return (
    <div className="space-y-1">
      <div
        className="flex h-2 overflow-hidden rounded-full bg-zinc-800"
        role="img"
        aria-label={`Bullish ${pct(bullish)}, neutral ${pct(neutral)}, bearish ${pct(bearish)}`}
      >
        <span className="bg-emerald-500" style={{ width: pct(bullish) }} />
        <span className="bg-zinc-500" style={{ width: pct(neutral) }} />
        <span className="bg-rose-500" style={{ width: pct(bearish) }} />
      </div>
      <div className="flex justify-between font-mono text-[10px] tabular-nums">
        <span className="text-emerald-400">bull {pct(bullish)}</span>
        <span className="text-zinc-500">neutral {pct(neutral)}</span>
        <span className="text-rose-400">bear {pct(bearish)}</span>
      </div>
    </div>
  )
}

function SubredditRow({ sub }: { sub: RedditSubredditSummary }) {
  const withTickers =
    sub.posts > 0 && sub.posts_with_tickers != null
      ? `${Math.round((sub.posts_with_tickers / sub.posts) * 100)}%`
      : '—'
  const top = Object.entries(sub.top_tickers ?? {}).slice(0, 3)

  return (
    <tr className="border-t border-zinc-800/70">
      <td className="py-1.5 pr-2 font-mono text-[11px] text-zinc-200">
        <a
          href={`https://www.reddit.com/r/${sub.subreddit}`}
          target="_blank"
          rel="noreferrer"
          className="hover:underline"
        >
          r/{sub.subreddit}
        </a>
      </td>
      <td className="py-1.5 pr-2 text-right font-mono text-[11px] tabular-nums text-zinc-400">{sub.posts}</td>
      <td className="py-1.5 pr-2 text-right font-mono text-[11px] tabular-nums text-zinc-400">{withTickers}</td>
      <td className={`py-1.5 pr-2 text-right font-mono text-[11px] tabular-nums ${moodTone(sub.mood)}`}>
        {formatSigned(sub.sentiment_score)}
      </td>
      <td className="py-1.5 font-mono text-[10px] text-zinc-400">
        {top.length > 0 ? top.map(([symbol, count]) => `${symbol} ${count}`).join(' · ') : '—'}
      </td>
    </tr>
  )
}

/**
 * Whole-run analytics next to the ticker ranking: overall mood, how much was
 * scraped, and how each subreddit contributed (issue #185).
 */
export default function RedditSummaryPanel({ data }: Props) {
  if (!data.available || !data.captured_at) return null

  const bySubreddit = data.by_subreddit ?? []
  const rising = data.rising ?? []
  const breakdown = data.sentiment_breakdown ?? {}

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-[13px] font-semibold text-zinc-100">Reddit Summary</h2>
        {data.window_hours != null && (
          <span className="font-mono text-[10px] text-zinc-500">last {data.window_hours}h</span>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex items-baseline gap-2">
          <span className="text-[11px] text-zinc-500">Overall mood</span>
          <span className={`text-sm font-semibold capitalize ${moodTone(data.mood)}`}>
            {data.mood ?? 'neutral'}
          </span>
          <span className={`font-mono text-[11px] tabular-nums ${moodTone(data.mood)}`}>
            {formatSigned(data.sentiment_score)}
          </span>
        </div>
        <SentimentBar breakdown={breakdown} />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Stat label="Posts in window" value={data.posts_in_window ?? '—'} />
        <Stat label="Posts scraped" value={data.posts_analyzed ?? '—'} />
        <Stat label="Subreddits" value={data.subreddits.length} />
        <Stat label="Tickers" value={data.tickers.length} />
      </div>

      {rising.length > 0 && (
        <div className="font-mono text-[11px]">
          <span className="text-zinc-500">rising: </span>
          <span className="text-emerald-400">{rising.join(', ')}</span>
        </div>
      )}

      {bySubreddit.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="font-mono text-[10px] text-zinc-600">
                <th className="pb-1 pr-2 font-normal">subreddit</th>
                <th className="pb-1 pr-2 text-right font-normal">posts</th>
                <th className="pb-1 pr-2 text-right font-normal" title="Posts that mention at least one ticker">
                  w/ ticker
                </th>
                <th className="pb-1 pr-2 text-right font-normal">sent</th>
                <th className="pb-1 font-normal">top tickers</th>
              </tr>
            </thead>
            <tbody>
              {bySubreddit.map((sub) => (
                <SubredditRow key={sub.subreddit} sub={sub} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
