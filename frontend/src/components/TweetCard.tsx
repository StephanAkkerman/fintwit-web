import type { Tweet } from '../types'

export default function TweetCard({
  t,
  onUserClick,
}: {
  t: Tweet
  onUserClick?: (screenName: string) => void
}) {
  return (
    <article className="rounded-2xl shadow p-4 bg-white dark:bg-zinc-900">
      <header className="flex items-center gap-3">
        <img
          src={t.user_img}
          alt=""
          className={`h-10 w-10 rounded-full ${onUserClick ? 'cursor-pointer' : ''}`}
          onClick={() => onUserClick?.(t.user_screen_name)}
        />
        <div
          className={`min-w-0 ${onUserClick ? 'cursor-pointer' : ''}`}
          onClick={() => onUserClick?.(t.user_screen_name)}
        >
          <div className="font-semibold truncate hover:underline">{t.user_name}</div>
          <div className="text-sm text-zinc-500">@{t.user_screen_name}</div>
        </div>
        <a
          className="ml-auto text-sm text-blue-600 hover:underline"
          href={t.url}
          target="_blank"
          rel="noreferrer"
        >
          Open
        </a>
      </header>

      <p className="mt-3 whitespace-pre-wrap text-sm">{t.text}</p>

      {t.media?.length > 0 && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          {t.media.map((m, i) => (
            <a key={i} href={m.url} target="_blank" rel="noreferrer">
              <img src={m.url} alt={m.type} className="rounded-xl w-full object-cover" />
            </a>
          ))}
        </div>
      )}

      <footer className="mt-3 flex flex-wrap gap-2 text-xs text-zinc-500">
        {t.tickers?.map((sym) => (
          <span key={sym} className="px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800">
            ${sym}
          </span>
        ))}
        {t.hashtags?.map((tag) => (
          <span key={tag} className="px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800">
            #{tag}
          </span>
        ))}
      </footer>
    </article>
  )
}