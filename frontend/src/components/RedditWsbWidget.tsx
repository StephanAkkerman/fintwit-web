import { useState } from 'react'
import { ExternalLink, Images, Play } from 'lucide-react'
import { useRedditWsb } from '../hooks/useRedditWsb'
import type { RedditPost } from '../types'

function formatAgo(createdUtc: number): string {
  if (!createdUtc) return 'unknown'
  const deltaSeconds = Math.max(0, Math.floor(Date.now() / 1000) - createdUtc)
  if (deltaSeconds < 60) return `${deltaSeconds}s ago`
  if (deltaSeconds < 3600) return `${Math.floor(deltaSeconds / 60)}m ago`
  if (deltaSeconds < 86400) return `${Math.floor(deltaSeconds / 3600)}h ago`
  return `${Math.floor(deltaSeconds / 86400)}d ago`
}

interface Props {
  subreddit?: string
  limit?: number
}

function subredditLabel(subreddit: string): string {
  return subreddit.toLowerCase() === 'wallstreetbets' ? 'WallStreetBets' : `r/${subreddit}`
}

function domainOf(url: string | null | undefined): string | null {
  if (!url) return null
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return null
  }
}

// Reddit bodies are Markdown; for a two-line teaser the syntax is just noise.
function excerpt(text: string, max = 280): string {
  const plain = text
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_~`>#]+/g, '')
    .replace(/\u200B/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  return plain.length > max ? `${plain.slice(0, max).trimEnd()}…` : plain
}

function Preview({ post }: { post: RedditPost }) {
  const [failed, setFailed] = useState(false)
  const src = post.image_urls?.[0]
  if (!src || failed) return null

  const extra = post.media_type === 'gallery' ? post.image_urls.length - 1 : 0

  return (
    <a
      href={post.url}
      target="_blank"
      rel="noreferrer"
      className="relative block h-20 w-20 shrink-0 overflow-hidden rounded-lg bg-zinc-200 sm:h-24 sm:w-24 dark:bg-zinc-800"
      aria-label={`Open ${post.media_type ?? 'post'} preview`}
    >
      <img
        src={src}
        alt=""
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        className={`h-full w-full object-cover ${post.over_18 ? 'scale-110 blur-md' : ''}`}
      />
      {post.over_18 && (
        <span className="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-white">
          NSFW
        </span>
      )}
      {post.media_type === 'video' && !post.over_18 && (
        <span className="absolute inset-0 flex items-center justify-center">
          <span className="rounded-full bg-black/60 p-1.5">
            <Play className="h-3.5 w-3.5 fill-white text-white" aria-hidden="true" />
          </span>
        </span>
      )}
      {extra > 0 && (
        <span className="absolute bottom-1 right-1 flex items-center gap-0.5 rounded bg-black/70 px-1 text-[10px] font-semibold text-white">
          <Images className="h-3 w-3" aria-hidden="true" />+{extra}
        </span>
      )}
    </a>
  )
}

function PostCard({ post }: { post: RedditPost }) {
  const description = excerpt(post.description || '')
  const linkDomain = post.media_type === 'link' ? domainOf(post.link_url) : null
  const ratio = post.upvote_ratio ? `${Math.round(post.upvote_ratio * 100)}% upvoted` : null

  return (
    <article className="flex gap-3 rounded-lg border border-zinc-200 bg-zinc-50 p-2.5 dark:border-zinc-800 dark:bg-zinc-900/60">
      <div className="min-w-0 flex-1">
        {post.flair && (
          <span className="mb-1 inline-block max-w-full truncate rounded bg-zinc-200 px-1.5 py-0.5 text-[10px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
            {post.flair}
          </span>
        )}
        <a
          href={post.url}
          target="_blank"
          rel="noreferrer"
          className="line-clamp-2 text-sm font-semibold text-zinc-900 hover:underline dark:text-zinc-100"
        >
          {post.title}
        </a>
        {description && (
          <p className="mt-1 line-clamp-3 text-xs text-zinc-600 dark:text-zinc-400">{description}</p>
        )}
        {linkDomain && post.link_url && (
          <a
            href={post.link_url}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-flex items-center gap-1 text-[11px] text-sky-600 hover:underline dark:text-sky-400"
          >
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
            {linkDomain}
          </a>
        )}
        <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[11px] text-zinc-500">
          <span>u/{post.author || 'unknown'}</span>
          <span>{post.score} upvotes</span>
          {ratio && <span>{ratio}</span>}
          <span>{post.num_comments} comments</span>
          <span>{formatAgo(post.created_utc)}</span>
        </div>
      </div>
      <Preview post={post} />
    </article>
  )
}

export default function RedditWsbWidget({ subreddit = 'wallstreetbets', limit = 8 }: Props) {
  const { data, loading, error } = useRedditWsb(limit, subreddit)
  const label = subredditLabel(subreddit)

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">{label} Radar</h2>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          Reddit
        </span>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, idx) => (
            <div key={idx} className="h-20 animate-pulse rounded-lg bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load {label} posts.</p>
      ) : data.length === 0 ? (
        <p className="text-sm text-zinc-500">No {label} posts available right now.</p>
      ) : (
        <div className="space-y-2">
          {data.map((post) => (
            <PostCard key={post.id} post={post} />
          ))}
        </div>
      )}
    </div>
  )
}
