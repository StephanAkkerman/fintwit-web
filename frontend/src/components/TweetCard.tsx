import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Tweet } from '../types'
import { hasChartSignal } from '../utils/tweetSignals'

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function fmtPrice(value: number): string {
  return `$${value.toLocaleString(undefined, {
    minimumFractionDigits: value < 1 ? 4 : 2,
    maximumFractionDigits: value < 1 ? 4 : 2,
  })}`
}

function fmtChangePercent(value: number): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

function parseFinancialSymbols(text: string): { tickers: string[]; hashtags: string[] } {
  const tickerMatches = [...text.matchAll(/(?<!\w)\$([a-z][a-z0-9]{0,9})\b/gi)]
  const hashtagMatches = [...text.matchAll(/(?<!\w)#([a-z][a-z0-9_]{0,29})\b/gi)]

  const tickers = [...new Set(tickerMatches.map((m) => m[1].toUpperCase()))]
  const hashtags = [...new Set(hashtagMatches.map((m) => m[1].toUpperCase()))]
  return { tickers, hashtags }
}

export default function TweetCard({
  t,
  onTickerSelect,
}: {
  t: Tweet
  onTickerSelect?: (ticker: string) => void
}) {
  const createdAt = t.created_at ? new Date(t.created_at) : null
  const timeLabel = createdAt
    ? createdAt.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
    : null
  const hasQuoteEmbed = /(^|\n)\s*>\s*/.test(t.text ?? '')
  const allMedia = t.media ?? []
  let quotedMediaIndex = -1
  if (hasQuoteEmbed) {
    for (let i = allMedia.length - 1; i >= 0; i -= 1) {
      if (allMedia[i]?.type === 'photo') {
        quotedMediaIndex = i
        break
      }
    }
  }
  const quotedMedia = quotedMediaIndex >= 0 ? allMedia[quotedMediaIndex] : undefined
  const inlineMedia = allMedia.filter((_, i) => i !== quotedMediaIndex)
  const showInlineMediaBeforeQuote = hasQuoteEmbed && inlineMedia.length > 0
  const parsedSymbols = parseFinancialSymbols(t.text ?? '')
  const tickerBadges = [...new Set([...(t.tickers ?? []), ...parsedSymbols.tickers].map((v) => v.toUpperCase()))]
  const hashtagBadges = [...new Set([...(t.hashtags ?? []), ...parsedSymbols.hashtags].map((v) => v.toUpperCase()))]
  const assets = (t.assets ?? []).filter((asset) => asset?.symbol)
  const hasChart = hasChartSignal(t)
  const sentimentLabel = t.sentiment_label?.toUpperCase() ?? null
  const sentimentEmoji = t.sentiment_emoji ?? null
  const sentimentClass =
    sentimentLabel === 'BULLISH'
      ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
      : sentimentLabel === 'BEARISH'
        ? 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
        : 'bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200'

  return (
    <article className="rounded-2xl shadow p-4 bg-white dark:bg-zinc-900">
      <header className="flex items-center gap-3">
        <img src={t.user_img} alt="" className="h-10 w-10 rounded-full" />
        <div className="min-w-0">
          <div className="font-semibold truncate">{t.user_name}</div>
          <div className="text-sm text-zinc-500">@{t.user_screen_name}</div>
        </div>
        <div className="ml-auto flex flex-col items-end gap-0.5">
          <a
            className="text-sm text-blue-600 hover:underline"
            href={t.url}
            target="_blank"
            rel="noreferrer"
          >
            Open
          </a>
          {timeLabel && (
            <span className="text-xs text-zinc-400">{timeLabel}</span>
          )}
        </div>
      </header>

      <div className="mt-3 text-sm leading-6 text-zinc-800 dark:text-zinc-200">
        {showInlineMediaBeforeQuote && (
          <div className="mb-3 grid grid-cols-2 gap-2">
            {inlineMedia.map((m, i) => (
              <a key={i} href={m.url} target="_blank" rel="noreferrer">
                <img src={m.url} alt={m.type} className="rounded-xl w-full object-cover" />
              </a>
            ))}
          </div>
        )}

        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
            a: ({ href, children }) => (
              <a
                href={href}
                target="_blank"
                rel="noreferrer"
                className="text-blue-600 dark:text-blue-400 hover:underline"
              >
                {children}
              </a>
            ),
            blockquote: ({ children }) => (
              <blockquote className="my-3 overflow-hidden rounded-2xl border border-zinc-300 bg-white/70 shadow-sm transition-colors hover:border-zinc-400 dark:border-zinc-700 dark:bg-zinc-900/60 dark:hover:border-zinc-500">
                <div className="flex items-center gap-1.5 border-b border-zinc-200 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M7 17h6v-6H9V7H5v6a4 4 0 0 0 4 4h2" />
                    <path d="M17 17h2a4 4 0 0 0 4-4V7h-4v4h4" />
                  </svg>
                  <span>Quoted post</span>
                </div>
                <div className="px-3 py-2 text-zinc-800 dark:text-zinc-200 [&_p]:mb-1.5 [&_p:last-child]:mb-0 [&_p:first-child_a]:font-semibold">
                  {children}
                </div>
                {quotedMedia && (
                  <a
                    href={quotedMedia.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block border-t border-zinc-200 dark:border-zinc-700"
                  >
                    <img
                      src={quotedMedia.url}
                      alt="Quoted media"
                      className="max-h-[28rem] w-full object-contain bg-zinc-100/70 dark:bg-zinc-800/60"
                    />
                  </a>
                )}
              </blockquote>
            ),
            ul: ({ children }) => <ul className="my-2 list-disc pl-5">{children}</ul>,
            ol: ({ children }) => <ol className="my-2 list-decimal pl-5">{children}</ol>,
            li: ({ children }) => <li className="my-1">{children}</li>,
            code: ({ children }) => (
              <code className="rounded bg-zinc-100 px-1 py-0.5 text-xs dark:bg-zinc-800">
                {children}
              </code>
            ),
          }}
        >
          {t.text}
        </ReactMarkdown>
      </div>

      {!showInlineMediaBeforeQuote && inlineMedia.length > 0 && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          {inlineMedia.map((m, i) => (
            <a key={i} href={m.url} target="_blank" rel="noreferrer">
              <img src={m.url} alt={m.type} className="rounded-xl w-full object-cover" />
            </a>
          ))}
        </div>
      )}

      {assets.length > 0 && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {assets.map((asset) => {
            const financials = asset.financials
            const hasPrice = typeof financials?.price === 'number'
            const hasChange = typeof financials?.change_percent === 'number'
            const change = hasChange ? (financials?.change_percent as number) : 0
            const changeClass =
              change > 0
                ? 'text-emerald-600 dark:text-emerald-400'
                : change < 0
                  ? 'text-rose-600 dark:text-rose-400'
                  : 'text-zinc-500 dark:text-zinc-400'

            return (
              <div
                key={asset.symbol}
                className="rounded-xl border border-zinc-200 bg-zinc-50/70 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-800/50"
              >
                <div className="flex items-center justify-between gap-2">
                  {onTickerSelect ? (
                    <button
                      type="button"
                      onClick={() => onTickerSelect(asset.symbol.toUpperCase())}
                      aria-label={`Filter by $${asset.symbol.toUpperCase()}`}
                      className="font-semibold text-zinc-800 underline-offset-2 hover:underline dark:text-zinc-100"
                    >
                      ${asset.symbol}
                    </button>
                  ) : (
                    <div className="font-semibold text-zinc-800 dark:text-zinc-100">
                      ${asset.symbol}
                    </div>
                  )}
                  {asset.kind && (
                    <span className="rounded-full bg-zinc-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300">
                      {asset.kind}
                    </span>
                  )}
                </div>

                {asset.name && (
                  <div className="truncate text-[11px] text-zinc-500 dark:text-zinc-400">{asset.name}</div>
                )}

                <div className="mt-1 flex items-center justify-between gap-2 text-sm">
                  {hasPrice && financials?.website ? (
                    <a
                      href={financials.website}
                      target="_blank"
                      rel="noreferrer"
                      className="font-semibold text-zinc-900 underline-offset-2 hover:underline dark:text-zinc-100"
                    >
                      {fmtPrice(financials?.price as number)}
                    </a>
                  ) : (
                    <span className="font-semibold text-zinc-900 dark:text-zinc-100">
                      {hasPrice ? fmtPrice(financials?.price as number) : 'N/A'}
                    </span>
                  )}
                  <span className={`font-semibold ${changeClass}`}>
                    {hasChange ? fmtChangePercent(change) : 'N/A'}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      )}

      <footer className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-500">
        <div className="flex flex-wrap gap-2">
          {hasChart && (
            <span
              aria-label="Chart tweet"
              className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
            >
              <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 3v18h18" />
                <path d="M7 14l4-4 3 3 5-6" />
              </svg>
              Chart
            </span>
          )}
          {(sentimentLabel || sentimentEmoji) && (
            <span
              aria-label="Tweet sentiment"
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${sentimentClass}`}
              title={
                typeof t.sentiment_score === 'number'
                  ? `Sentiment confidence: ${(t.sentiment_score * 100).toFixed(1)}%`
                  : undefined
              }
            >
              <span>{sentimentEmoji ?? '🦆'}</span>
              <span>{sentimentLabel ?? 'SENTIMENT'}</span>
            </span>
          )}
          {tickerBadges.map((sym) => (
            <span key={sym} className="px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800">
              ${sym}
            </span>
          ))}
          {hashtagBadges.map((tag) => (
            <span key={tag} className="px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800">
              #{tag}
            </span>
          ))}
        </div>

        <div className="flex gap-3 shrink-0">
          {t.views > 0 && (
            <span title="Views" className="flex items-center gap-1">
              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              {fmt(t.views)}
            </span>
          )}
          {t.replies > 0 && (
            <span title="Replies" className="flex items-center gap-1">
              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
              {fmt(t.replies)}
            </span>
          )}
          {t.retweets > 0 && (
            <span title="Retweets" className="flex items-center gap-1">
              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>
              {fmt(t.retweets)}
            </span>
          )}
          {t.likes > 0 && (
            <span title="Likes" className="flex items-center gap-1">
              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
              {fmt(t.likes)}
            </span>
          )}
        </div>
      </footer>
    </article>
  )
}