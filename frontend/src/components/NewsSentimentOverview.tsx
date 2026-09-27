import {
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { CompanyNewsArticle, CompanyNewsSentimentSummary } from '../types'
import { displayLabel, emojiForLabel, sentimentBadgeClass, type SentimentLabel } from '../utils/sentiment'

const LABEL_COLOR: Record<SentimentLabel, string> = {
  BULLISH: '#10b981',
  NEUTRAL: '#a1a1aa',
  BEARISH: '#f43f5e',
}

const BAR_CLASS: Record<SentimentLabel, string> = {
  BULLISH: 'bg-emerald-500',
  NEUTRAL: 'bg-zinc-400 dark:bg-zinc-600',
  BEARISH: 'bg-rose-500',
}

const LABEL_ORDER: SentimentLabel[] = ['BULLISH', 'NEUTRAL', 'BEARISH']

export function fmtScore(score: number): string {
  return `${score > 0 ? '+' : ''}${score.toFixed(2)}`
}

function countFor(summary: CompanyNewsSentimentSummary, label: SentimentLabel): number {
  if (label === 'BULLISH') return summary.bullish
  if (label === 'BEARISH') return summary.bearish
  return summary.neutral
}

type TimelinePoint = {
  time: number
  score: number
  label: SentimentLabel
  title: string
  source: string
}

function toTimeline(articles: CompanyNewsArticle[]): TimelinePoint[] {
  const points: TimelinePoint[] = []
  for (const article of articles) {
    if (article.sentiment_score == null || !article.sentiment_label) continue
    const time = new Date(article.date).getTime()
    if (Number.isNaN(time)) continue
    points.push({
      time,
      score: article.sentiment_score,
      label: article.sentiment_label,
      title: article.title,
      source: article.source ?? 'Unknown source',
    })
  }
  return points.sort((a, b) => a.time - b.time)
}

const DAY_MS = 24 * 60 * 60 * 1000

/** One tick per local day (thinned to at most ~6), so no date label repeats. */
function dayTicks(points: TimelinePoint[]): number[] {
  if (points.length === 0) return []
  const first = new Date(points[0].time)
  first.setHours(0, 0, 0, 0)
  const last = points[points.length - 1].time
  const days: number[] = []
  for (let t = first.getTime(); t <= last; t += DAY_MS) days.push(t)
  const step = Math.ceil(days.length / 6)
  return days.filter((_, i) => i % step === 0)
}

function TimelineTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: TimelinePoint }> }) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload
  return (
    <div className="max-w-xs rounded-md border border-zinc-200 bg-white px-2 py-1.5 text-xs shadow-md dark:border-zinc-700 dark:bg-zinc-900">
      <p className="font-semibold text-zinc-900 dark:text-zinc-100">{point.title}</p>
      <p className="mt-0.5 text-zinc-500">
        {point.source} &middot; {new Date(point.time).toLocaleString()}
      </p>
      <p className="mt-0.5 text-zinc-600 dark:text-zinc-300">
        {emojiForLabel(point.label)} {displayLabel(point.label)} ({fmtScore(point.score)})
      </p>
    </div>
  )
}

type NewsSentimentOverviewProps = {
  symbol: string
  summary: CompanyNewsSentimentSummary
  articles: CompanyNewsArticle[]
}

/**
 * One-glance read of a symbol's news flow (issue #180): which way the
 * headlines lean, how they split, and how that moved over time — so the
 * reader only has to open the articles that matter.
 */
export default function NewsSentimentOverview({ symbol, summary, articles }: NewsSentimentOverviewProps) {
  if (summary.analyzed === 0 || !summary.label || summary.mean_score == null) {
    return (
      <p className="mb-3 text-xs text-zinc-500" data-testid="news-sentiment-unavailable">
        Sentiment analysis is unavailable (the sentiment model is not loaded).
      </p>
    )
  }

  const timeline = toTimeline(articles)
  const ticks = dayTicks(timeline)
  const label = summary.label

  return (
    <div className="mb-4 space-y-3" data-testid="news-sentiment-overview">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-zinc-600 dark:text-zinc-300">News on {symbol} leans</span>
        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${sentimentBadgeClass(label)}`}>
          {emojiForLabel(label)} {displayLabel(label)}
        </span>
        <span className="text-xs text-zinc-500">
          avg {fmtScore(summary.mean_score)} across {summary.analyzed} headline
          {summary.analyzed === 1 ? '' : 's'}
        </span>
      </div>

      <div>
        <div
          className="flex h-2.5 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800"
          role="img"
          aria-label={`${summary.bullish} bullish, ${summary.neutral} neutral, ${summary.bearish} bearish`}
        >
          {LABEL_ORDER.map((key) => {
            const count = countFor(summary, key)
            if (count === 0) return null
            return (
              <div
                key={key}
                className={BAR_CLASS[key]}
                style={{ width: `${(count / summary.analyzed) * 100}%` }}
              />
            )
          })}
        </div>
        <div className="mt-1 flex gap-3 text-[11px] text-zinc-500">
          {LABEL_ORDER.map((key) => (
            <span key={key} className="flex items-center gap-1">
              <span className={`inline-block h-2 w-2 rounded-full ${BAR_CLASS[key]}`} />
              {countFor(summary, key)} {displayLabel(key).toLowerCase()}
            </span>
          ))}
        </div>
      </div>

      {timeline.length > 1 && (
        <div className="h-32 w-full" data-testid="news-sentiment-timeline">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <ReferenceLine y={0} stroke="currentColor" className="text-zinc-300 dark:text-zinc-700" />
              <XAxis
                type="number"
                dataKey="time"
                domain={[ticks[0] ?? 'dataMin', 'dataMax']}
                ticks={ticks}
                scale="time"
                tickFormatter={(value: number) =>
                  new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
                }
                tick={{ fontSize: 10 }}
                stroke="currentColor"
                className="text-zinc-400"
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                type="number"
                dataKey="score"
                domain={[-1, 1]}
                ticks={[-1, 0, 1]}
                width={28}
                tick={{ fontSize: 10 }}
                stroke="currentColor"
                className="text-zinc-400"
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<TimelineTooltip />} cursor={false} />
              <Scatter
                data={timeline}
                isAnimationActive={false}
                shape={(props: { cx?: number; cy?: number; payload?: TimelinePoint }) => (
                  <circle
                    cx={props.cx}
                    cy={props.cy}
                    r={5}
                    fill={props.payload ? LABEL_COLOR[props.payload.label] : LABEL_COLOR.NEUTRAL}
                    fillOpacity={0.85}
                  />
                )}
              />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
