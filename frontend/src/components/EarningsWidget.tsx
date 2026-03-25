import { useEffect, useState } from 'react'

type EarningsData = {
  ticker: string
  next_earnings_date: string
  timestamp: number
}

export default function EarningsWidget({ ticker }: { ticker: string }) {
  const [data, setData] = useState<EarningsData | null>(null)
  const [error, setError] = useState<boolean>(false)

  useEffect(() => {
    fetch(`/api/earnings/${ticker}`)
      .then((res) => {
        if (!res.ok) throw new Error('Network response was not ok')
        return res.json()
      })
      .then((d) => setData(d))
      .catch((_) => setError(true))
  }, [ticker])

  if (error) return null

  const formattedDate = data
    ? new Date(data.timestamp * 1000).toLocaleDateString(undefined, {
        weekday: 'short',
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      })
    : ''

  return (
    <div className="bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-4 flex flex-col space-y-2 mb-4">
      <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider">{ticker} Next Earnings</h2>
      {data ? (
        <div className="flex items-center space-x-4">
          <div className="text-xl font-bold text-zinc-900 dark:text-zinc-100">{formattedDate}</div>
          <div className="flex flex-col text-sm">
             <span className="font-medium text-zinc-700 dark:text-zinc-300">Estimated Date</span>
          </div>
        </div>
      ) : (
        <div className="animate-pulse h-8 bg-zinc-200 dark:bg-zinc-800 rounded-md w-48"></div>
      )}
    </div>
  )
}
