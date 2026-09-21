import { useMemo, useState } from 'react'
import { RedditTrendsWidget } from './RedditTrendsWidget'
import RedditWsbWidget from './RedditWsbWidget'
import { useRedditCategories } from '../hooks/useRedditCategories'

type RedditTab = 'trends' | 'posts'

const TABS: { id: RedditTab; label: string }[] = [
  { id: 'trends', label: 'Trends' },
  { id: 'posts', label: 'Posts' },
]

// Always offered even if /api/reddit/categories hasn't loaded (or the
// reddit-stock-analyzer package isn't installed) yet — this is the one
// subreddit the raw-posts feed supports out of the box.
const DEFAULT_SUBREDDIT = 'wallstreetbets'

export default function RedditSection() {
  const [tab, setTab] = useState<RedditTab>('trends')
  const [subreddit, setSubreddit] = useState(DEFAULT_SUBREDDIT)
  const { data: categories } = useRedditCategories()

  // WallStreetBets stays first and always present regardless of what the
  // catalogue returns, since it's the subreddit this section starts on.
  const subredditOptions = useMemo(() => {
    const fromApi = categories.default ?? []
    return Array.from(new Set([DEFAULT_SUBREDDIT, ...fromApi]))
  }, [categories])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div
          role="tablist"
          aria-label="Reddit views"
          className="inline-flex rounded-xl bg-zinc-100 p-1 dark:bg-zinc-900"
        >
          {TABS.map(({ id, label }) => {
            const active = tab === id
            return (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setTab(id)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                  active
                    ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-800 dark:text-zinc-100'
                    : 'text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'
                }`}
              >
                {label}
              </button>
            )
          })}
        </div>

        {tab === 'posts' && (
          <label className="flex items-center gap-2 text-xs text-zinc-500">
            <span>Subreddit</span>
            <select
              value={subreddit}
              onChange={(event) => setSubreddit(event.target.value)}
              className="rounded-lg border border-zinc-200 bg-white px-2 py-1 text-xs font-semibold text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200"
            >
              {subredditOptions.map((sub) => (
                <option key={sub} value={sub}>
                  r/{sub}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {tab === 'trends' ? (
        <RedditTrendsWidget limit={20} />
      ) : (
        <RedditWsbWidget subreddit={subreddit} limit={10} />
      )}
    </div>
  )
}
