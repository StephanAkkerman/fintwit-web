import { useState } from 'react'
import SignaBestTradesWidget from './SignaBestTradesWidget'
import SignaLiveFeedWidget from './SignaLiveFeedWidget'

type SignaTab = 'best' | 'feed'

const TABS: { id: SignaTab; label: string }[] = [
  { id: 'best', label: 'Best Trades' },
  { id: 'feed', label: 'Live Feed' },
]

export default function SignaSection() {
  const [tab, setTab] = useState<SignaTab>('best')

  return (
    <div className="space-y-4">
      <div
        role="tablist"
        aria-label="Signa views"
        className="inline-flex rounded-xl bg-zinc-100 p-1 dark:bg-zinc-900"
      >
        {TABS.map(({ id, label }) => {
          const active = tab === id
          return (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setTab(id)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                active
                  ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-800 dark:text-zinc-100'
                  : 'text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'
              }`}
            >
              {label}
            </button>
          )
        })}
      </div>

      {tab === 'best' ? <SignaBestTradesWidget /> : <SignaLiveFeedWidget />}
    </div>
  )
}
