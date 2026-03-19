import { useState } from 'react'

export default function EarningsCheck() {
  const [stock, setStock] = useState('')
  const [result, setResult] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const checkEarnings = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!stock) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await fetch(`/api/earnings/${stock}`)
      if (!res.ok) {
        if (res.status === 404) {
          throw new Error('No earnings data found for this stock.')
        }
        throw new Error('Failed to fetch earnings data.')
      }
      const data = await res.json()
      const dateStr = new Date(data.next_earnings_date).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      })
      setResult(`The next earnings date for ${data.stock} is ${dateStr}.`)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-4 shadow-sm">
      <h2 className="text-lg font-bold mb-2 text-zinc-800 dark:text-zinc-200">Check Earnings Date</h2>
      <form onSubmit={checkEarnings} className="flex gap-2 mb-3">
        <input
          type="text"
          value={stock}
          onChange={(e) => setStock(e.target.value.toUpperCase())}
          placeholder="Enter stock ticker (e.g. AAPL)"
          className="flex-1 bg-zinc-100 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          type="submit"
          disabled={loading || !stock}
          className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white font-medium rounded-lg px-4 py-2 text-sm transition-colors"
        >
          {loading ? 'Checking...' : 'Check'}
        </button>
      </form>
      {result && <p className="text-sm text-green-600 dark:text-green-400 font-medium">{result}</p>}
      {error && <p className="text-sm text-red-600 dark:text-red-400 font-medium">{error}</p>}
    </div>
  )
}
