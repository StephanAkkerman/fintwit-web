import { useState } from 'react'
import { useAnalystRatings } from '../hooks/useAnalystRatings'

export default function AnalystRatingsWidget() {
  const [ticker, setTicker] = useState('AAPL')
  const [searchInput, setSearchInput] = useState('AAPL')
  const { ratings, loading, error } = useAnalystRatings(ticker)

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    if (searchInput.trim()) {
      setTicker(searchInput.trim().toUpperCase())
    }
  }

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900 mb-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-100">
          Analyst Ratings
        </h2>
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Enter ticker..."
            className="rounded border border-zinc-300 bg-zinc-50 px-2 py-1 text-sm text-zinc-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
          />
          <button
            type="submit"
            className="rounded bg-blue-600 px-3 py-1 text-sm font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-zinc-900"
          >
            Search
          </button>
        </form>
      </div>

      {loading ? (
        <div className="py-8 text-center text-sm text-zinc-500">Loading {ticker} ratings...</div>
      ) : error ? (
        <div className="py-8 text-center text-sm text-red-500">Error: {error}</div>
      ) : ratings.length === 0 ? (
        <div className="py-8 text-center text-sm text-zinc-500">No ratings found for {ticker}</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-200 dark:border-zinc-800">
                <th className="pb-2 font-medium text-zinc-500 dark:text-zinc-400">Date</th>
                <th className="pb-2 font-medium text-zinc-500 dark:text-zinc-400">Price Target</th>
                <th className="pb-2 font-medium text-zinc-500 dark:text-zinc-400">Rating</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {ratings.map((rating, idx) => (
                <tr key={idx} className="group hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
                  <td className="py-3 pr-4 text-zinc-900 dark:text-zinc-100 whitespace-nowrap">
                    {rating.date}
                  </td>
                  <td className="py-3 pr-4 text-zinc-900 dark:text-zinc-100 whitespace-nowrap">
                    {rating.price_target}
                  </td>
                  <td className="py-3 pr-4 text-zinc-900 dark:text-zinc-100 whitespace-nowrap">
                    {rating.rating}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
