import type { BackendStatus } from '../types'

function formatStarted(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatMemory(mb: number) {
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${Math.round(mb)} MB`
}

/** One line of backend health, turning amber once it has been restarting. */
export default function BackendStatusLine({ status }: { status: BackendStatus | null }) {
  if (!status?.started_at) return null

  const restarts = status.unexpected_restarts_24h
  return (
    <p
      className={`text-xs ${restarts > 0 ? 'text-amber-700 dark:text-amber-400' : 'text-zinc-500'}`}
    >
      Running since {formatStarted(status.started_at)}
      {restarts > 0 && (
        <>
          {' · '}
          <span
            className="font-semibold"
            title={
              status.last_unexpected_restart
                ? `Last seen before a restart: ${formatStarted(status.last_unexpected_restart)}. Check the host for an out-of-memory kill.`
                : undefined
            }
          >
            {restarts} unexpected restart{restarts === 1 ? '' : 's'} in 24h
          </span>
        </>
      )}
      {status.peak_memory_mb != null && ` · peak memory ${formatMemory(status.peak_memory_mb)}`}
    </p>
  )
}
