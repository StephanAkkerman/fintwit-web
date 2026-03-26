import { useState } from 'react'

type EarningsData = {
  ticker: string
  next_earnings_date: number
  formatted_date: string
}

export default function EarningsWidget() {
  const [ticker, setTicker] = useState('')
  const [data, setData] = useState<EarningsData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!ticker.trim()) return

    setLoading(true)
    setError(null)
    setData(null)

    try {
      const res = await fetch(`/api/earnings?ticker=${encodeURIComponent(ticker.trim())}`)
      if (!res.ok) {
        if (res.status === 404) {
           throw new Error(`Earnings date not found for ${ticker.toUpperCase()}`)
        }
        throw new Error('Network response was not ok')
      }
      const json = await res.json()
      setData(json)
    } catch (err: any) {
      setError(err.message || 'An error occurred')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-4 flex flex-col space-y-3 mb-4">
      <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider">Next Earnings Date</h2>
      <form onSubmit={handleSearch} className="flex space-x-2">
        <input
          type="text"
          placeholder="Enter stock ticker (e.g. AAPL)"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          className="flex-1 px-3 py-1.5 bg-white dark:bg-black border border-zinc-300 dark:border-zinc-700 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-zinc-400 dark:focus:ring-zinc-500"
        />
        <button
          type="submit"
          disabled={loading || !ticker.trim()}
          className="px-4 py-1.5 bg-zinc-800 dark:bg-zinc-100 text-white dark:text-black font-medium text-sm rounded-md disabled:opacity-50 transition-opacity"
        >
          {loading ? 'Searching...' : 'Search'}
        </button>
      </form>

      {error && <div className="text-sm text-red-500">{error}</div>}

      {data && (
        <div className="flex flex-col space-y-1 pt-2 border-t border-zinc-200 dark:border-zinc-800">
          <div className="text-lg font-bold">{data.ticker}</div>
          <div className="text-sm text-zinc-700 dark:text-zinc-300">
            {data.formatted_date}
          </div>
        </div>
      )}
    </div>
  )
}
