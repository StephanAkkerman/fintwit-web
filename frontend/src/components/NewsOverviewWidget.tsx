import { useNewsOverview } from '../hooks/useNewsOverview'
import type { NewsOverviewResponse, NewsStory } from '../types'
import { displayLabel, emojiForLabel, sentimentBadgeClass } from '../utils/sentiment'
import { fmtScore } from './NewsSentimentOverview'

function fmtTime(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}

/** One line on the shape of the news flow: volume, lean and what it is about. */
export function briefingLine(data: NewsOverviewResponse): string {
  const outlets = new Set(data.articles.map((a) => a.source).filter(Boolean)).size
  const parts = [`${plural(data.articles.length, 'headline')} from ${plural(outlets, 'outlet')}`]
  if (data.sentiment.label) parts.push(`leaning ${displayLabel(data.sentiment.label).toLowerCase()}`)
  const themes = data.themes.slice(0, 3).map((t) => t.name)
  if (themes.length > 0) parts.push(`mostly about ${themes.join(', ')}`)
  return `${parts.join(', ')}.`
}

type StoryProps = {
  story: NewsStory
  rank: number
  onTickerClick?: (ticker: string) => void
}

function Story({ story, rank, onTickerClick }: StoryProps) {
  return (
    <li className="flex gap-3 border-b border-zinc-100 pb-3 last:border-0 last:pb-0 dark:border-zinc-800">
      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-zinc-900 text-xs font-bold text-white dark:bg-zinc-100 dark:text-zinc-900">
        {rank}
      </span>
      <div className="min-w-0 flex-1">
        <a
          href={story.url}
          target="_blank"
          rel="noreferrer"
          className="text-sm font-semibold text-zinc-900 hover:underline dark:text-zinc-100"
        >
          {story.title}
        </a>
        {story.summary && <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">{story.summary}</p>}
        <p className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-500">
          {story.sentiment_label && (
            <span
              className={`rounded-full px-1.5 py-px font-semibold ${sentimentBadgeClass(story.sentiment_label)}`}
              title={story.sentiment_score != null ? `FinTwitBERT score ${fmtScore(story.sentiment_score)}` : undefined}
            >
              {emojiForLabel(story.sentiment_label)} {displayLabel(story.sentiment_label)}
            </span>
          )}
          <span>
            {story.article_count > 1
              ? `${plural(story.article_count, 'headline')} · ${story.sources.join(', ')}`
              : story.source ?? 'Unknown source'}{' '}
            &middot; {fmtTime(story.date)}
          </span>
          {story.themes.map((theme) => (
            <span key={theme} className="rounded-full bg-indigo-50 px-1.5 py-px text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
              {theme}
            </span>
          ))}
          {story.symbols.map((symbol) => (
            <button
              key={symbol}
              type="button"
              onClick={() => onTickerClick?.(symbol)}
              className="rounded bg-zinc-100 px-1.5 py-px font-mono text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
            >
              {symbol}
            </button>
          ))}
        </p>
        {story.related.length > 0 && (
          <details className="mt-1 text-[11px] text-zinc-500">
            <summary className="cursor-pointer select-none">Also covered as</summary>
            <ul className="mt-1 space-y-0.5 pl-3">
              {story.related.map((link) => (
                <li key={link.url}>
                  <a href={link.url} target="_blank" rel="noreferrer" className="hover:underline">
                    {link.title}
                  </a>
                  {link.source && <span> · {link.source}</span>}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </li>
  )
}

type NewsOverviewWidgetProps = {
  /** A ticker chip was clicked: load it in the company news below. */
  onTickerClick?: (ticker: string) => void
}

export default function NewsOverviewWidget({ onTickerClick }: NewsOverviewWidgetProps = {}) {
  const { data, loading, error } = useNewsOverview()
  const storyUrls = new Set(data.top_stories.flatMap((s) => [s.url, ...s.related.map((r) => r.url)]))
  const latest = data.articles.filter((a) => !storyUrls.has(a.url)).slice(0, 15)

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Market briefing</h2>
        {data.generated_at && <span className="text-[11px] text-zinc-500">Updated {fmtTime(data.generated_at)}</span>}
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-14 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load market news.</p>
      ) : data.top_stories.length === 0 ? (
        <p className="text-sm text-zinc-500">No market news available right now.</p>
      ) : (
        <>
          <p className="mb-3 text-sm text-zinc-700 dark:text-zinc-300">{briefingLine(data)}</p>
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">Top stories</h3>
          <ol className="space-y-3" aria-label="Top stories">
            {data.top_stories.map((story, i) => (
              <Story key={story.url} story={story} rank={i + 1} onTickerClick={onTickerClick} />
            ))}
          </ol>
          {latest.length > 0 && (
            <>
              <h3 className="mb-2 mt-4 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                More headlines
              </h3>
              <ul className="space-y-1.5" aria-label="More headlines">
                {latest.map((article) => (
                  <li key={article.url} className="text-xs">
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-zinc-800 hover:underline dark:text-zinc-200"
                    >
                      {article.title}
                    </a>
                    <span className="text-zinc-500">
                      {' '}
                      &middot; {article.source ?? 'Unknown source'} &middot; {fmtTime(article.date)}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </div>
  )
}
