import { FormEvent, useEffect, useState } from 'react'

type ErrorResponse = { detail?: string }

type Status = 'idle' | 'loading' | 'ready' | 'unconfigured' | 'error'

async function parseError(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as ErrorResponse
    if (data.detail) return data.detail
  } catch {
    // ignore parse failures, fall through to generic message
  }
  return `Request failed with status ${res.status}`
}

export default function AccessAllowlistPanel() {
  const [emails, setEmails] = useState<string[]>([])
  const [status, setStatus] = useState<Status>('idle')
  const [message, setMessage] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [busyEmail, setBusyEmail] = useState<string | null>(null)

  const load = async () => {
    setStatus('loading')
    setMessage('')
    try {
      const res = await fetch('/api/admin/access-emails')
      if (res.status === 503) {
        setStatus('unconfigured')
        setMessage(await parseError(res))
        return
      }
      if (!res.ok) throw new Error(await parseError(res))
      const data = (await res.json()) as { emails: string[] }
      setEmails(data.emails)
      setStatus('ready')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof Error ? error.message : 'Failed to load allowlist.')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const onInvite = async (ev: FormEvent<HTMLFormElement>) => {
    ev.preventDefault()
    setMessage('')
    try {
      const res = await fetch('/api/admin/access-emails', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: newEmail }),
      })
      if (!res.ok) throw new Error(await parseError(res))
      const data = (await res.json()) as { emails: string[] }
      setEmails(data.emails)
      setNewEmail('')
      setStatus('ready')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof Error ? error.message : 'Failed to invite that email.')
    }
  }

  const onRemove = async (email: string) => {
    setBusyEmail(email)
    setMessage('')
    try {
      const res = await fetch(`/api/admin/access-emails/${encodeURIComponent(email)}`, {
        method: 'DELETE',
      })
      if (!res.ok) throw new Error(await parseError(res))
      const data = (await res.json()) as { emails: string[] }
      setEmails(data.emails)
      setStatus('ready')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof Error ? error.message : 'Failed to remove that email.')
    } finally {
      setBusyEmail(null)
    }
  }

  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">
        Cloudflare Access allowlist
      </h2>
      <p className="mt-1 text-xs text-zinc-500">
        Only these emails can log in to the publicly-tunneled dashboard. Verified with a
        one-time code Cloudflare emails them — no password to share.
      </p>

      {status === 'unconfigured' && (
        <p className="mt-4 text-xs text-amber-600 dark:text-amber-400">{message}</p>
      )}

      {status !== 'unconfigured' && (
        <>
          <form className="mt-4 flex flex-wrap items-end gap-2" onSubmit={onInvite}>
            <label className="grid gap-1 text-xs font-medium text-zinc-500">
              Invite by email
              <input
                type="email"
                required
                value={newEmail}
                onChange={(ev) => setNewEmail(ev.target.value)}
                placeholder="friend@example.com"
                aria-label="Email to invite"
                className="rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm text-zinc-900 outline-none ring-zinc-400 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
              />
            </label>
            <button
              type="submit"
              className="rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
            >
              Invite
            </button>
          </form>

          {message && (
            <p className="mt-2 text-xs text-red-500" role="alert">
              {message}
            </p>
          )}

          <ul className="mt-4 grid gap-2">
            {status === 'loading' && <li className="text-xs text-zinc-500">Loading...</li>}
            {status === 'ready' && emails.length === 0 && (
              <li className="text-xs text-zinc-500">No one is allowed in yet.</li>
            )}
            {emails.map((email) => (
              <li
                key={email}
                className="flex items-center justify-between rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-sm text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900/50 dark:text-zinc-200"
              >
                {email}
                <button
                  type="button"
                  onClick={() => void onRemove(email)}
                  disabled={busyEmail === email}
                  aria-label={`Remove ${email}`}
                  className="text-xs font-medium text-red-500 hover:text-red-600 disabled:opacity-50"
                >
                  {busyEmail === email ? 'Removing...' : 'Remove'}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
