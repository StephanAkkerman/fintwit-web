import { useStockFearGreed } from '../hooks/useStockFearGreed'

const STATUS_COLOR: Record<string, string> = {
  'extreme fear': 'text-red-500',
  fear: 'text-orange-500',
  neutral: 'text-zinc-500 dark:text-zinc-400',
  greed: 'text-lime-500',
  'extreme greed': 'text-green-500',
}

function statusColor(status: string): string {
  return STATUS_COLOR[status.toLowerCase()] ?? 'text-zinc-500 dark:text-zinc-400'
}

export default function StockFearGreedWidget() {
  const { data, loading, error } = useStockFearGreed()

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-500">
        Stock Fear &amp; Greed Index
      </h2>

      {loading ? (
        <div className="h-10 w-32 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
      ) : error || !data ? (
        <p className="text-sm text-red-500">Could not load the Fear &amp; Greed index.</p>
      ) : (
        <div className="flex items-center space-x-4">
          <div className={`text-3xl font-bold ${statusColor(data.status)}`}>{data.value}</div>
          <div className="flex flex-col text-sm">
            <span className={`font-medium ${statusColor(data.status)}`}>{data.status}</span>
            {data.change && (
              <span
                className={
                  data.change.includes('+')
                    ? 'text-green-500'
                    : data.change.includes('-')
                      ? 'text-red-500'
                      : 'text-zinc-500'
                }
              >
                {data.change}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
