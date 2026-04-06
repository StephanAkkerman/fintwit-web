import { useMemo } from 'react'
import { useRedditWsb } from '../hooks/useRedditWsb'

function formatAgo(createdUtc: number): string {
  if (!createdUtc) return 'unknown'
  const deltaSeconds = Math.max(0, Math.floor(Date.now() / 1000) - createdUtc)
  if (deltaSeconds < 60) return `${deltaSeconds}s ago`
  if (deltaSeconds < 3600) return `${Math.floor(deltaSeconds / 60)}m ago`
  if (deltaSeconds < 86400) return `${Math.floor(deltaSeconds / 3600)}h ago`
  return `${Math.floor(deltaSeconds / 86400)}d ago`
}

export default function RedditWsbWidget() {
  const { data, loading, error } = useRedditWsb(8)

  const posts = useMemo(() => data.slice(0, 6), [data])

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">WallStreetBets Radar</h2>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          Reddit
        </span>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, idx) => (
            <div key={idx} className="h-12 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load WallStreetBets posts.</p>
      ) : posts.length === 0 ? (
        <p className="text-sm text-zinc-500">No WallStreetBets posts available right now.</p>
      ) : (
        <div className="space-y-2">
          {posts.map((post) => (
            <article
              key={post.id}
              className="rounded-lg border border-zinc-200 bg-zinc-50 p-2.5 dark:border-zinc-800 dark:bg-zinc-900/60"
            >
              <a
                href={post.url}
                target="_blank"
                rel="noreferrer"
                className="line-clamp-2 text-sm font-semibold text-zinc-900 hover:underline dark:text-zinc-100"
              >
                {post.title}
              </a>
              <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-zinc-500">
                <span>u/{post.author || 'unknown'}</span>
                <span>{post.score} upvotes</span>
                <span>{post.num_comments} comments</span>
                <span>{formatAgo(post.created_utc)}</span>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
