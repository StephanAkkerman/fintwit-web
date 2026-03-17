import TweetCard from './components/TweetCard'
import MarketMoversWidget from './components/MarketMoversWidget'
import { useTweets } from './hooks/useTweets'

export default function App() {
  const { tweets } = useTweets('') // same-origin API (proxied in dev)
  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black text-zinc-900 dark:text-zinc-100">
      <div className="max-w-6xl mx-auto p-4 flex flex-col md:flex-row gap-6 items-start">
        <main className="flex-1 w-full space-y-3">
          <header className="sticky top-0 z-10 bg-zinc-50/80 dark:bg-black/80 backdrop-blur p-2 -mx-2">
            <h1 className="text-2xl font-bold">X Stream</h1>
            <p className="text-sm text-zinc-500">Live tweets · SSE · Vite</p>
          </header>
          {tweets.map((t) => (
            <TweetCard key={t.id} t={t} />
          ))}
        </main>

        <aside className="w-full md:w-80 shrink-0 sticky top-4">
          <MarketMoversWidget />
        </aside>
      </div>
    </div>
  )
}