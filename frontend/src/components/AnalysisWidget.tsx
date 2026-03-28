import { useEffect, useState } from 'react'

type AnalysisRating = {
  date: string
  target: string
  rating: string
}

type AnalysisData = {
  stock: string
  analysis: AnalysisRating[]
}

export default function AnalysisWidget({ ticker }: { ticker: string }) {
  const [data, setData] = useState<AnalysisData | null>(null)
  const [error, setError] = useState<boolean>(false)
  const [loading, setLoading] = useState<boolean>(false)

  useEffect(() => {
    if (!ticker) {
      setData(null)
      setError(false)
      return
    }

    setLoading(true)
    setError(false)
    setData(null)

    fetch(`/api/analysis/${ticker}`)
      .then((res) => {
        if (!res.ok) throw new Error('Network response was not ok')
        return res.json()
      })
      .then((d) => {
        setData(d)
        setLoading(false)
      })
      .catch((_) => {
        setError(true)
        setLoading(false)
      })
  }, [ticker])

  if (!ticker) return null

  return (
    <div className="bg-zinc-100 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-4 flex flex-col space-y-3 mb-4">
      <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider">
        Analyst Ratings: {ticker.toUpperCase()}
      </h2>

      {loading && (
        <div className="animate-pulse space-y-2">
           <div className="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-full"></div>
           <div className="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-full"></div>
           <div className="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-5/6"></div>
        </div>
      )}

      {error && !loading && (
        <div className="text-sm text-red-500">
          Could not fetch analysis for {ticker.toUpperCase()}.
        </div>
      )}

      {data && !loading && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left text-zinc-700 dark:text-zinc-300">
            <thead className="text-xs text-zinc-500 uppercase bg-zinc-50 dark:bg-zinc-800/50">
              <tr>
                <th scope="col" className="px-3 py-2 rounded-tl-lg rounded-bl-lg">Date</th>
                <th scope="col" className="px-3 py-2">Price Target</th>
                <th scope="col" className="px-3 py-2 rounded-tr-lg rounded-br-lg">Rating</th>
              </tr>
            </thead>
            <tbody>
              {data.analysis.map((item, idx) => (
                <tr key={idx} className="border-b border-zinc-200 dark:border-zinc-800 last:border-0">
                  <td className="px-3 py-2 whitespace-nowrap">{item.date}</td>
                  <td className="px-3 py-2">{item.target}</td>
                  <td className="px-3 py-2 font-medium">{item.rating}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
