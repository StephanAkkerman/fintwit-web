import { FormEvent, useMemo, useState } from 'react'

type DebugResponse = {
  id?: number
  text?: string
  user_name?: string
  user_screen_name?: string
  tickers?: string[]
  hashtags?: string[]
}

function parseCsv(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function parseLines(value: string): string[] {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

export default function DebugAdminPanel() {
  const [text, setText] = useState('Bullish setup on $AAPL and #BTC')
  const [title, setTitle] = useState('')
  const [userName, setUserName] = useState('Debug User')
  const [screenName, setScreenName] = useState('debuguser')
  const [tickers, setTickers] = useState('')
  const [hashtags, setHashtags] = useState('')
  const [mediaUrls, setMediaUrls] = useState('')
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const [response, setResponse] = useState<DebugResponse | null>(null)

  const mediaList = useMemo(() => parseLines(mediaUrls), [mediaUrls])

  const onSubmit = async (ev: FormEvent<HTMLFormElement>) => {
    ev.preventDefault()
    setStatus('submitting')
    setMessage('')

    try {
      const payload = {
        text,
        title,
        user_name: userName,
        user_screen_name: screenName,
        user_img: '',
        tickers: parseCsv(tickers),
        hashtags: parseCsv(hashtags),
        media: mediaList,
        media_types: mediaList.map(() => 'photo'),
      }

      const res = await fetch('/api/debug/tweet', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!res.ok) {
        throw new Error(`Request failed with status ${res.status}`)
      }

      const data = (await res.json()) as DebugResponse
      setResponse(data)
      setStatus('success')
      setMessage('Debug tweet injected successfully.')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof Error ? error.message : 'Failed to inject debug tweet.')
    }
  }

  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Debug Admin Panel</h2>
      <p className="mt-1 text-xs text-zinc-500">Post synthetic tweets to validate ingestion and timeline rendering.</p>

      <form className="mt-4 grid gap-3" onSubmit={onSubmit}>
        <label className="grid gap-1 text-xs font-medium text-zinc-500">
          Tweet text
          <textarea
            value={text}
            onChange={(ev) => setText(ev.target.value)}
            rows={3}
            aria-label="Debug tweet text"
            className="rounded-lg border border-zinc-300 bg-white px-2.5 py-2 text-sm text-zinc-900 outline-none ring-zinc-400 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
        </label>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1 text-xs font-medium text-zinc-500">
            User name
            <input
              value={userName}
              onChange={(ev) => setUserName(ev.target.value)}
              aria-label="Debug user name"
              className="rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm text-zinc-900 outline-none ring-zinc-400 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            />
          </label>

          <label className="grid gap-1 text-xs font-medium text-zinc-500">
            Screen name
            <input
              value={screenName}
              onChange={(ev) => setScreenName(ev.target.value)}
              aria-label="Debug screen name"
              className="rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm text-zinc-900 outline-none ring-zinc-400 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            />
          </label>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1 text-xs font-medium text-zinc-500">
            Tickers (comma-separated)
            <input
              value={tickers}
              onChange={(ev) => setTickers(ev.target.value)}
              placeholder="AAPL,BTC"
              aria-label="Debug tickers"
              className="rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm text-zinc-900 outline-none ring-zinc-400 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            />
          </label>

          <label className="grid gap-1 text-xs font-medium text-zinc-500">
            Hashtags (comma-separated)
            <input
              value={hashtags}
              onChange={(ev) => setHashtags(ev.target.value)}
              placeholder="btc,stocks"
              aria-label="Debug hashtags"
              className="rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm text-zinc-900 outline-none ring-zinc-400 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            />
          </label>
        </div>

        <label className="grid gap-1 text-xs font-medium text-zinc-500">
          Media URLs (one per line, optional)
          <textarea
            value={mediaUrls}
            onChange={(ev) => setMediaUrls(ev.target.value)}
            rows={2}
            placeholder="https://example.com/chart.png"
            aria-label="Debug media urls"
            className="rounded-lg border border-zinc-300 bg-white px-2.5 py-2 text-sm text-zinc-900 outline-none ring-zinc-400 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
        </label>

        <label className="grid gap-1 text-xs font-medium text-zinc-500">
          Title (optional)
          <input
            value={title}
            onChange={(ev) => setTitle(ev.target.value)}
            aria-label="Debug title"
            className="rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm text-zinc-900 outline-none ring-zinc-400 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
        </label>

        <div className="flex items-center gap-2">
          <button
            type="submit"
            disabled={status === 'submitting'}
            className="rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            {status === 'submitting' ? 'Injecting...' : 'Inject Debug Tweet'}
          </button>

          {message && (
            <span
              className={`text-xs ${status === 'error' ? 'text-red-500' : 'text-emerald-600 dark:text-emerald-400'}`}
            >
              {message}
            </span>
          )}
        </div>
      </form>

      {response && (
        <div className="mt-4 rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-xs dark:border-zinc-700 dark:bg-zinc-900/50">
          <div className="font-semibold text-zinc-700 dark:text-zinc-200">Last injected tweet</div>
          <div className="mt-1 text-zinc-500 dark:text-zinc-400">ID: {response.id ?? 'n/a'}</div>
          <div className="mt-1 text-zinc-700 dark:text-zinc-200">{response.text ?? ''}</div>
          {(response.tickers?.length ?? 0) > 0 && (
            <div className="mt-1 text-zinc-500 dark:text-zinc-400">Tickers: {response.tickers?.join(', ')}</div>
          )}
          {(response.hashtags?.length ?? 0) > 0 && (
            <div className="mt-1 text-zinc-500 dark:text-zinc-400">Hashtags: {response.hashtags?.join(', ')}</div>
          )}
        </div>
      )}
    </section>
  )
}
