import type { XStreamStatus } from '../types'

const COOKIE_STEPS =
  'Log into x.com, open DevTools (F12) → Application → Cookies → https://x.com, and copy the auth_token and ct0 values'

/** Explains an empty or stale timeline when the X stream isn't running. */
export default function XStreamNotice({ status }: { status: XStreamStatus | null }) {
  const state = status?.state
  if (state !== 'disabled' && state !== 'auth_failed' && state !== 'stalled') return null

  const title =
    state === 'stalled'
      ? 'X timeline stalled'
      : state === 'auth_failed'
        ? 'X session expired'
        : 'X timeline not connected'
  return (
    <div
      role="status"
      className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200"
    >
      <p className="font-semibold">{title}</p>
      {state === 'stalled' ? (
        <p className="mt-1">
          The stream has stopped processing new posts ({status?.detail ?? 'no recent progress'}).
          Check the backend logs, and restart the backend if it doesn't recover.
        </p>
      ) : (
        <p className="mt-1">
          {state === 'auth_failed'
            ? `X rejected the saved session (${status?.detail ?? 'unauthorized'}), so no new tweets are coming in. `
            : 'The rest of the dashboard works without it; the tweet timeline needs your X session. '}
          {COOKIE_STEPS}, then set <code>X_AUTH_TOKEN</code> and <code>X_CT0</code> in{' '}
          <code>.env</code> and restart the backend.
        </p>
      )}
    </div>
  )
}
