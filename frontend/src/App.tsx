import TweetCard from './components/TweetCard'
import FearGreedWidget from './components/FearGreedWidget'
import TreemapWidget from './components/TreemapWidget'
import { useTweets } from './hooks/useTweets'

export default function App() {
  const { tweets } = useTweets('') // same-origin API (proxied in dev)
  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black text-zinc-900 dark:text-zinc-100">
      <main className="mx-auto max-w-3xl p-4 space-y-3">
        <header className="sticky top-0 z-10 bg-inherit/60 backdrop-blur p-2 -mx-2">
          <h1 className="text-2xl font-bold">X Stream</h1>
          <p className="text-sm text-zinc-500">Live tweets · SSE · Vite</p>
        </header>
        <FearGreedWidget />
        <TreemapWidget />
        {tweets.map((t) => (
          <TweetCard key={t.id} t={t} />
        ))}
      </main>
    </div>
  )
}