import { useEffect, useState } from 'react'

type FearGreedData = {
  value: number
  change: number
  status: string
}

export default function FearGreedWidget() {
  const [data, setData] = useState<FearGreedData | null>(null)
  const [error, setError] = useState<boolean>(false)

  useEffect(() => {
    fetch('/api/fear-greed')
      .then((res) => {
        if (!res.ok) throw new Error('Network response was not ok')
        return res.json()
      })
      .then((d) => setData(d))
      .catch((_) => setError(true))
  }, [])

  if (error) return null

  return (
    <div className="bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-4 flex flex-col space-y-2 mb-4">
      <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider">Fear & Greed Index</h2>
      {data ? (
        <div className="flex items-center space-x-4">
          <div className="text-3xl font-bold">{data.value}</div>
          <div className="flex flex-col text-sm">
            <span className="font-medium text-zinc-700 dark:text-zinc-300">{data.status}</span>
            <span className={data.change > 0 ? 'text-green-500' : data.change < 0 ? 'text-red-500' : 'text-zinc-500'}>
              {`${data.change > 0 ? '+' : ''}${data.change.toFixed(2)}% ${data.change > 0 ? '📈' : data.change < 0 ? '📉' : '➖'}`}
            </span>
          </div>
        </div>
      ) : (
        <div className="animate-pulse h-10 bg-zinc-200 dark:bg-zinc-800 rounded-md w-32"></div>
      )}
    </div>
  )
}
