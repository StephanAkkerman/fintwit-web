import { useState } from 'react'
import TweetCard from './components/TweetCard'
import FearGreedWidget from './components/FearGreedWidget'
import AnalysisWidget from './components/AnalysisWidget'
import { useTweets } from './hooks/useTweets'

export default function App() {
  const { tweets } = useTweets('') // same-origin API (proxied in dev)
  const [ticker, setTicker] = useState('')
  const [searchInput, setSearchInput] = useState('')

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setTicker(searchInput.trim())
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black text-zinc-900 dark:text-zinc-100">
      <main className="mx-auto max-w-3xl p-4 space-y-3">
        <header className="sticky top-0 z-10 bg-inherit/60 backdrop-blur p-2 -mx-2 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">X Stream</h1>
            <p className="text-sm text-zinc-500">Live tweets · SSE · Vite</p>
          </div>
          <form onSubmit={handleSearch} className="flex gap-2">
            <input
              type="text"
              placeholder="Enter stock ticker (e.g. AAPL)"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="px-3 py-1 bg-white dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="submit"
              className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium transition-colors"
            >
              Analyze
            </button>
          </form>
        </header>

        {ticker && <AnalysisWidget ticker={ticker} />}

        <FearGreedWidget />

        {tweets.map((t) => (
          <TweetCard key={t.id} t={t} />
        ))}
      </main>
    </div>
  )
}