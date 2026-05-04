import { useEffect, useState } from 'react'
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

function formatAssetKind(kind: string | null | undefined): string | null {
  if (!kind) return null

  const normalized = kind.trim().toUpperCase()
  if (!normalized) return null

  const labels: Record<string, string> = {
    EQUITY: 'Stock',
    ETF: 'ETF',
    CRYPTO: 'Crypto',
    INDEX: 'Index',
    FUTURE: 'Future',
    FOREX: 'Forex',
    COMMODITY: 'Commodity',
    UNKNOWN: 'Unknown',
  }

  return labels[normalized] ?? normalized
}

function parseFinancialSymbols(text: string): { tickers: string[]; hashtags: string[] } {
  const tickerMatches = [...text.matchAll(/(?<!\w)\$([a-z][a-z0-9]{0,9})\b/gi)]
  const hashtagMatches = [...text.matchAll(/(?<!\w)#([a-z][a-z0-9_]{0,29})\b/gi)]

  const tickers = [...new Set(tickerMatches.map((m) => m[1].toUpperCase()))]
  const hashtags = [...new Set(hashtagMatches.map((m) => m[1].toUpperCase()))]
  return { tickers, hashtags }
}

const FILTER_HREF_PREFIX = '#filter-'

function linkifySymbols(text: string): string {
  // Single-pass replacement: match $TICKER or #hashtag together so the
  // hashtag branch can't re-match inside an already-replaced cashtag href.
  return text.replace(
    /(?<!\w)(?:\$([A-Za-z][A-Za-z0-9]{0,9})|#([A-Za-z][A-Za-z0-9_]{0,29}))\b/g,
    (_, tickerSym, hashtagSym) => {
      if (tickerSym) {
        const sym = tickerSym.toUpperCase()
        return `[$${sym}](${FILTER_HREF_PREFIX}${sym})`
      }
      const tag = hashtagSym.toUpperCase()
      return `[#${hashtagSym}](${FILTER_HREF_PREFIX}${tag})`
    },
  )
}

function parseTweetDate(createdAt: string | null | undefined): Date | null {
  if (!createdAt) return null

  const hasOffset = /([zZ]|[+-]\d{2}:\d{2})$/.test(createdAt)
  const normalized = hasOffset ? createdAt : `${createdAt}Z`
  const parsed = new Date(normalized)

  if (Number.isNaN(parsed.getTime())) {
    return null
  }

  return parsed
}

function isRepostTweet(t: Tweet): boolean {
  const title = String(t.title ?? '').toLowerCase()
  return title.includes('retweeted') && Boolean(t.quoted_tweet)
}

type QuoteMeta = {
  displayName: string | null
  screenName: string | null
  url: string | null
  createdAt: Date | null
  userImg: string | null
}

function SubscriberOnlyBadge({ ariaLabel }: { ariaLabel: string }) {
  return (
    <span
      aria-label={ariaLabel}
      title="Subscribers only"
      className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-violet-600 text-white ring-1 ring-violet-400 dark:bg-violet-500 dark:ring-violet-300"
    >
      <svg className="h-2.5 w-2.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12 2.5l2.78 5.63 6.22.9-4.5 4.38 1.06 6.2L12 16.66 6.44 19.6l1.06-6.2L3 9.03l6.22-.9L12 2.5z" />
      </svg>
    </span>
  )
}

const X_SNOWFLAKE_EPOCH = 1_288_834_974_657n

function decodeXStatusTimestamp(statusId: string): Date | null {
  try {
    const tweetId = BigInt(statusId)
    const timestampMs = Number((tweetId >> 22n) + X_SNOWFLAKE_EPOCH)

    if (!Number.isFinite(timestampMs)) {
      return null
    }

    const parsed = new Date(timestampMs)
    if (Number.isNaN(parsed.getTime())) {
      return null
    }

    return parsed
  } catch {
    return null
  }
}

function normalizeScreenName(value: string | null | undefined): string | null {
  if (!value) {
    return null
  }

  const cleaned = value.trim().replace(/^@+/, '')
  if (!cleaned) {
    return null
  }

  const match = cleaned.match(/^([A-Za-z0-9_]{1,15})$/)
  return match ? match[1] : null
}

function buildQuotedUrl(
  screenName: string | null,
  quoteId: number | string | null | undefined,
  fallbackUrl: string | null
): string | null {
  const normalized = normalizeScreenName(screenName)
  const normalizedId = quoteId == null ? '' : String(quoteId).trim()

  if (normalized && /^\d+$/.test(normalizedId)) {
    return `https://x.com/${normalized}/status/${normalizedId}`
  }

  return fallbackUrl
}

function stripQuotedLeadHandleLine(text: string): string {
  if (!text || !/(^|\n)\s*>\s*/.test(text)) {
    return text
  }

  const lines = text.split('\n')
  const firstQuoteIndex = lines.findIndex((line) => /^\s*>/.test(line))
  if (firstQuoteIndex < 0) {
    return text
  }

  const candidate = lines[firstQuoteIndex].trim()
  const looksLikeQuoteLead =
    /^>\s*\[[^\]]+\]\(https?:\/\/(?:x|twitter)\.com\/[^\s)]+\)\s*:\s*$/i.test(candidate) ||
    /^>\s*@?[A-Za-z0-9_]{1,15}\s*:\s*$/i.test(candidate)

  if (!looksLikeQuoteLead) {
    return text
  }

  const nextQuoteLine = lines.slice(firstQuoteIndex + 1).find((line) => line.trim().length > 0)
  if (!nextQuoteLine || !/^\s*>/.test(nextQuoteLine)) {
    return text
  }

  lines.splice(firstQuoteIndex, 1)
  return lines.join('\n')
}

function hasMarkdownQuoteEmbed(text: string): boolean {
  if (!text || !/(^|\n)\s*>\s*/.test(text)) {
    return false
  }

  const lines = text.split('\n')
  const firstQuoteIndex = lines.findIndex((line) => /^\s*>/.test(line))
  if (firstQuoteIndex < 0) {
    return false
  }

  const candidate = lines[firstQuoteIndex].trim()
  const looksLikeQuoteLead =
    /^>\s*\[[^\]]+\]\(https?:\/\/(?:x|twitter)\.com\/[^[\s)]+\)\s*:\s*$/i.test(candidate) ||
    /^>\s*@?[A-Za-z0-9_]{1,15}\s*:\s*$/i.test(candidate)

  if (!looksLikeQuoteLead) {
    return false
  }

  return lines.slice(firstQuoteIndex + 1).some((line) => line.trim().length > 0 && /^\s*>/.test(line))
}

function extractQuoteMeta(t: Tweet): QuoteMeta {
  const quotedTweet = t.quoted_tweet ?? null
  const text = t.text ?? ''
  const quoteLines = text
    .split('\n')
    .map((line) => line.replace(/^\s*>\s?/, '').trim())
    .filter(Boolean)

  const firstQuoteLine = quoteLines[0] ?? ''
  const markdownUserMatch = firstQuoteLine.match(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/i)
  const quoteStatusUrlMatch = text.match(/https?:\/\/(?:x|twitter)\.com\/[^/\s]+\/status\/(\d+)/i)

  const fallbackQuotedUrl =
    t.quoted_url?.trim() ||
    quotedTweet?.url?.trim() ||
    markdownUserMatch?.[2]?.trim() ||
    quoteStatusUrlMatch?.[0] ||
    null

  const rawDisplayName =
    t.quoted_user_name?.trim() || quotedTweet?.user_name?.trim() || markdownUserMatch?.[1]?.trim() || null
  const profileNameFromUrl =
    fallbackQuotedUrl?.match(/https?:\/\/(?:x|twitter)\.com\/([A-Za-z0-9_]{1,15})/i)?.[1] ?? null

  const screenName =
    normalizeScreenName(t.quoted_user_screen_name) ||
    normalizeScreenName(quotedTweet?.user_screen_name) ||
    normalizeScreenName(rawDisplayName) ||
    normalizeScreenName(profileNameFromUrl)

  const quotedUrl = buildQuotedUrl(screenName, quotedTweet?.id, fallbackQuotedUrl)

  const displayName = rawDisplayName || (screenName ? `@${screenName}` : null)

  let createdAt = parseTweetDate(t.quoted_created_at) ?? parseTweetDate(quotedTweet?.created_at)
  if (!createdAt && quotedUrl) {
    const statusId = quotedUrl.match(/status\/(\d+)/i)?.[1]
    if (statusId) {
      createdAt = decodeXStatusTimestamp(statusId)
    }
  }

  const userImg = t.quoted_user_img?.trim() || quotedTweet?.user_img?.trim() || null

  return {
    displayName,
    screenName,
    url: quotedUrl,
    createdAt,
    userImg,
  }
}

export default function TweetCard({
  t,
  onTickerSelect,
  onUserSelect,
}: {
  t: Tweet
  onTickerSelect?: (ticker: string) => void
  onUserSelect?: (user: string) => void
}) {
  const [lightboxImage, setLightboxImage] = useState<{ url: string; alt: string } | null>(null)

  const isRepost = isRepostTweet(t)
  const headerTweet = isRepost && t.quoted_tweet ? t.quoted_tweet : t

  useEffect(() => {
    if (!lightboxImage) return

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const onKeyDown = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') {
        setLightboxImage(null)
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [lightboxImage])

  const createdAt = parseTweetDate(headerTweet.created_at)
  const timeLabel = createdAt
    ? createdAt.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
    : null
  const hasQuoteEmbed = !isRepost && (Boolean(t.quoted_tweet) || hasMarkdownQuoteEmbed(t.text ?? ''))
  const rawText = hasQuoteEmbed ? stripQuotedLeadHandleLine(t.text ?? '') : (t.text ?? '')
  const renderedText = onTickerSelect ? linkifySymbols(rawText) : rawText
  const allMedia = t.media ?? []
  const quotedTweetMedia = (t.quoted_tweet?.media ?? []).filter((m) => typeof m?.url === 'string' && !!m.url)
  const quotedMediaUrls = new Set(quotedTweetMedia.map((m) => m.url))

  let fallbackQuotedMediaIndex = -1
  if (hasQuoteEmbed && quotedTweetMedia.length === 0) {
    for (let i = allMedia.length - 1; i >= 0; i -= 1) {
      if (allMedia[i]?.type === 'photo') {
        fallbackQuotedMediaIndex = i
        break
      }
    }
  }

  const fallbackQuotedMedia = fallbackQuotedMediaIndex >= 0 ? allMedia[fallbackQuotedMediaIndex] : undefined
  const quotedMedia = quotedTweetMedia[0] ?? fallbackQuotedMedia
  const inlineMedia = allMedia.filter((m, i) => {
    if (typeof m?.url === 'string' && quotedMediaUrls.has(m.url)) {
      return false
    }
    return i !== fallbackQuotedMediaIndex
  })
  const showInlineMediaBeforeQuote = hasQuoteEmbed && inlineMedia.length > 0
  const parsedSymbols = parseFinancialSymbols(t.text ?? '')
  const tickerBadges = [...new Set([...(t.tickers ?? []), ...parsedSymbols.tickers].map((v) => v.toUpperCase()))]
  const hashtagBadges = [...new Set([...(t.hashtags ?? []), ...parsedSymbols.hashtags].map((v) => v.toUpperCase()))]
  const assets = (t.assets ?? []).filter((asset) => asset?.symbol)
  const hasChart = hasChartSignal(t)
  const sentimentLabel = t.sentiment_label?.toUpperCase() ?? null
  const sentimentEmoji = t.sentiment_emoji ?? null
  const quotedSentimentLabel = t.quoted_sentiment_label?.toUpperCase() ?? null
  const quotedSentimentEmoji = t.quoted_sentiment_emoji ?? null
  const quoteMeta = hasQuoteEmbed ? extractQuoteMeta(t) : null
  const quotedTimeLabel = quoteMeta?.createdAt
    ? quoteMeta.createdAt.toLocaleString(undefined, {
        dateStyle: 'medium',
        timeStyle: 'short',
      })
    : null
  const quotedHandle = quoteMeta?.screenName ? `@${quoteMeta.screenName}` : null
  const showQuotedHandle = Boolean(
    quotedHandle && quotedHandle.toLowerCase() !== (quoteMeta?.displayName ?? '').toLowerCase()
  )
  const showQuotedMetaLine = Boolean(showQuotedHandle || quotedTimeLabel)
  const isSubscriberOnly = Boolean(headerTweet.is_subscriber_only)
  const isQuotedSubscriberOnly = Boolean(t.quoted_tweet?.is_subscriber_only)
  const headerUserFilterValue = headerTweet.user_screen_name || headerTweet.user_name
  const sentimentClass =
    sentimentLabel === 'BULLISH'
      ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
      : sentimentLabel === 'BEARISH'
        ? 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
        : 'bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200'
  const quotedSentimentClass =
    quotedSentimentLabel === 'BULLISH'
      ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
      : quotedSentimentLabel === 'BEARISH'
        ? 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
        : 'bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200'

  return (
    <article className="rounded-2xl shadow p-4 bg-white dark:bg-zinc-900">
      <header className="flex items-center gap-3">
        {onUserSelect ? (
          <button
            type="button"
            onClick={() => onUserSelect(headerUserFilterValue)}
            aria-label={`Filter by user @${headerTweet.user_screen_name}`}
            className="shrink-0"
          >
            <img
              src={headerTweet.user_img}
              alt={`${headerTweet.user_name} avatar`}
              className="h-10 w-10 rounded-full"
            />
          </button>
        ) : (
          <img src={headerTweet.user_img} alt={`${headerTweet.user_name} avatar`} className="h-10 w-10 rounded-full" />
        )}
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-1.5">
            {onUserSelect ? (
              <button
                type="button"
                onClick={() => onUserSelect(headerUserFilterValue)}
                aria-label={`Filter by user @${headerTweet.user_screen_name}`}
                className="truncate text-left font-semibold hover:underline"
              >
                {headerTweet.user_name}
              </button>
            ) : (
              <div className="font-semibold truncate">{headerTweet.user_name}</div>
            )}
            {isSubscriberOnly && <SubscriberOnlyBadge ariaLabel="Subscribers-only post" />}
          </div>
          {onUserSelect ? (
            <button
              type="button"
              onClick={() => onUserSelect(headerUserFilterValue)}
              aria-label={`Filter by user @${headerTweet.user_screen_name}`}
              className="text-sm text-zinc-500 hover:underline"
            >
              @{headerTweet.user_screen_name}
            </button>
          ) : (
            <div className="text-sm text-zinc-500">@{headerTweet.user_screen_name}</div>
          )}
          {isRepost && (
            <div className="text-xs text-zinc-500">Reposted by {t.user_name}</div>
          )}
        </div>
        <div className="ml-auto flex flex-col items-end gap-0.5">
          <a
            className="text-sm text-blue-600 hover:underline"
            href={headerTweet.url}
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
              <button
                key={i}
                type="button"
                onClick={() => setLightboxImage({ url: m.url, alt: m.type || 'Tweet media' })}
                aria-label="Open image preview"
                className="overflow-hidden rounded-xl"
              >
                <img src={m.url} alt={m.type} className="rounded-xl w-full object-cover" />
              </button>
            ))}
          </div>
        )}

        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            p: ({ children }) => <p className="mb-2 whitespace-pre-wrap last:mb-0">{children}</p>,
            a: ({ href, children }) => {
              const filterIdx = href?.indexOf(FILTER_HREF_PREFIX) ?? -1
              if (filterIdx !== -1 && onTickerSelect) {
                const symbol = href!.slice(filterIdx + FILTER_HREF_PREFIX.length)
                return (
                  <button
                    type="button"
                    onClick={() => onTickerSelect(symbol)}
                    className="text-blue-500 dark:text-blue-400 hover:underline font-medium cursor-pointer"
                  >
                    {children}
                  </button>
                )
              }
              return (
                <a
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-600 dark:text-blue-400 hover:underline"
                >
                  {children}
                </a>
              )
            },
            blockquote: ({ children }) => (
              hasQuoteEmbed ? (
                <blockquote className="my-3 overflow-hidden rounded-2xl border border-zinc-300 bg-white/70 shadow-sm transition-colors hover:border-zinc-400 dark:border-zinc-700 dark:bg-zinc-900/60 dark:hover:border-zinc-500">
                  <div className="flex items-start justify-between gap-2 border-b border-zinc-200 px-3 py-2 dark:border-zinc-700">
                    <div className="flex min-w-0 items-start gap-2">
                      {quoteMeta?.userImg && (
                        <img
                          src={quoteMeta.userImg}
                          alt="Quoted user avatar"
                          className="mt-0.5 h-7 w-7 shrink-0 rounded-full"
                        />
                      )}
                      <div className="min-w-0">
                        <div className="flex min-w-0 items-center gap-1.5">
                          {quoteMeta?.url ? (
                            <a
                              href={quoteMeta.url}
                              target="_blank"
                              rel="noreferrer"
                              aria-label="Quoted tweet author"
                              className="truncate text-sm font-semibold text-zinc-900 hover:underline dark:text-zinc-100"
                            >
                              {quoteMeta.displayName ?? 'Quoted post'}
                            </a>
                          ) : (
                            <div className="truncate text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                              {quoteMeta?.displayName ?? 'Quoted post'}
                            </div>
                          )}
                          {isQuotedSubscriberOnly && (
                            <SubscriberOnlyBadge ariaLabel="Quoted subscribers-only post" />
                          )}
                        </div>
                        {showQuotedMetaLine && (
                          <div className="mt-0.5 flex items-center gap-1 text-[11px] text-zinc-500 dark:text-zinc-400">
                            {showQuotedHandle && <span>{quotedHandle}</span>}
                            {showQuotedHandle && quotedTimeLabel && <span aria-hidden="true">&middot;</span>}
                            {quotedTimeLabel && (
                              <time aria-label="Quoted tweet timestamp" dateTime={quoteMeta?.createdAt?.toISOString()}>
                                {quotedTimeLabel}
                              </time>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                    {(quotedSentimentLabel || quotedSentimentEmoji) && (
                      <span
                        aria-label="Quoted tweet sentiment"
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${quotedSentimentClass}`}
                        title={
                          typeof t.quoted_sentiment_score === 'number'
                            ? `Quoted sentiment confidence: ${(t.quoted_sentiment_score * 100).toFixed(1)}%`
                            : undefined
                        }
                      >
                        <span>{quotedSentimentEmoji ?? '🦆'}</span>
                        <span>{quotedSentimentLabel ?? 'SENTIMENT'}</span>
                      </span>
                    )}
                  </div>
                  <div className="px-3 py-2 text-zinc-800 dark:text-zinc-200 [&_p]:mb-1.5 [&_p:last-child]:mb-0 [&_p:first-child_a]:font-semibold">
                    {children}
                  </div>
                  {quotedMedia && (
                    <button
                      type="button"
                      onClick={() => setLightboxImage({ url: quotedMedia.url, alt: 'Quoted media' })}
                      aria-label="Open quoted image preview"
                      className="block w-full border-t border-zinc-200 dark:border-zinc-700"
                    >
                      <img
                        src={quotedMedia.url}
                        alt="Quoted media"
                        className="max-h-[28rem] w-full object-contain bg-zinc-100/70 dark:bg-zinc-800/60"
                      />
                    </button>
                  )}
                </blockquote>
              ) : (
                <div className="my-2 whitespace-pre-wrap text-zinc-800 dark:text-zinc-200">{children}</div>
              )
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
          {renderedText}
        </ReactMarkdown>
      </div>

      {!showInlineMediaBeforeQuote && inlineMedia.length > 0 && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          {inlineMedia.map((m, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setLightboxImage({ url: m.url, alt: m.type || 'Tweet media' })}
              aria-label="Open image preview"
              className="overflow-hidden rounded-xl"
            >
              <img src={m.url} alt={m.type} className="rounded-xl w-full object-cover" />
            </button>
          ))}
        </div>
      )}

      {assets.length > 0 && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {assets.map((asset) => {
            const financials = asset.financials
            const ticker = `$${asset.symbol}`
            const fullName =
              typeof asset.name === 'string' && asset.name.trim().length > 0 ? asset.name : ticker
            const typeLabel = formatAssetKind(asset.kind)
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
                      className="truncate text-left font-semibold text-zinc-800 underline-offset-2 hover:underline dark:text-zinc-100"
                    >
                      {ticker}
                    </button>
                  ) : (
                    <div className="truncate font-semibold text-zinc-800 dark:text-zinc-100">
                      {ticker}
                    </div>
                  )}
                  {typeLabel && (
                    <span className="rounded-full bg-zinc-200 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300">
                      {typeLabel}
                    </span>
                  )}
                </div>

                <div className="truncate text-[11px] text-zinc-500 dark:text-zinc-400">{fullName}</div>

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
          {tickerBadges.map((sym) =>
            onTickerSelect ? (
              <button
                key={sym}
                type="button"
                onClick={() => onTickerSelect(sym)}
                aria-label={`Filter by $${sym}`}
                className="px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer"
              >
                ${sym}
              </button>
            ) : (
              <span key={sym} className="px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800">
                ${sym}
              </span>
            )
          )}
          {hashtagBadges.map((tag) =>
            onTickerSelect ? (
              <button
                key={tag}
                type="button"
                onClick={() => onTickerSelect(tag)}
                aria-label={`Filter by #${tag}`}
                className="px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 cursor-pointer"
              >
                #{tag}
              </button>
            ) : (
              <span key={tag} className="px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800">
                #{tag}
              </span>
            )
          )}
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

      {lightboxImage && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Image preview"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          onClick={() => setLightboxImage(null)}
        >
          <div
            className="relative w-full max-w-5xl"
            onClick={(ev) => ev.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => setLightboxImage(null)}
              aria-label="Close image preview"
              className="absolute right-2 top-2 rounded-full bg-black/70 px-3 py-1 text-sm font-semibold text-white hover:bg-black"
            >
              Close
            </button>
            <img
              src={lightboxImage.url}
              alt={lightboxImage.alt}
              className="max-h-[85vh] w-full rounded-2xl object-contain"
            />
          </div>
        </div>
      )}
    </article>
  )
}