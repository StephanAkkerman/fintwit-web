import { useState } from 'react'
import TweetCard from './components/TweetCard'
import { useTweets } from './hooks/useTweets'

export default function App() {
  const { tweets } = useTweets('') // same-origin API (proxied in dev)
  const [selectedUser, setSelectedUser] = useState<string | null>(null)

  const filteredTweets = selectedUser
    ? tweets.filter((t) => t.user_screen_name === selectedUser)
    : tweets

  const userPreview = selectedUser ? filteredTweets[0] : null

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black text-zinc-900 dark:text-zinc-100">
      <main className="mx-auto max-w-3xl p-4 space-y-3">
        <header className="sticky top-0 z-10 bg-inherit/60 backdrop-blur p-2 -mx-2">
          {!selectedUser ? (
            <>
              <h1 className="text-2xl font-bold">X Stream</h1>
              <p className="text-sm text-zinc-500">Live tweets · SSE · Vite</p>
            </>
          ) : (
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSelectedUser(null)}
                className="p-2 -ml-2 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
                aria-label="Go back"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M19 12H5M12 19l-7-7 7-7" />
                </svg>
              </button>
              {userPreview && (
                <>
                  <img
                    src={userPreview.user_img}
                    alt=""
                    className="h-10 w-10 rounded-full"
                  />
                  <div className="min-w-0">
                    <div className="font-semibold truncate">{userPreview.user_name}</div>
                    <div className="text-sm text-zinc-500">
                      @{userPreview.user_screen_name}
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </header>
        {filteredTweets.map((t) => (
          <TweetCard
            key={t.id}
            t={t}
            onUserClick={!selectedUser ? setSelectedUser : undefined}
          />
        ))}
      </main>
    </div>
  )
}