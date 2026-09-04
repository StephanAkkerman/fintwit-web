import { useState } from 'react'
import type { Market, MoverCategory, MoverItem } from '../types'
import { useMoversExplorer } from '../hooks/useMoversExplorer'

const MARKETS: { value: Market; label: string }[] = [
  { value: 'usa', label: 'USA' },
  { value: 'uk', label: 'UK' },
  { value: 'india', label: 'India' },
  { value: 'australia', label: 'Australia' },
  { value: 'canada', label: 'Canada' },
  { value: 'crypto', label: 'Crypto' },
]

const CATEGORIES: { value: MoverCategory; label: string }[] = [
  { value: 'gainers', label: 'Gainers' },
  { value: 'losers', label: 'Losers' },
  { value: 'most_active', label: 'Most Active' },
  { value: 'penny_stocks', label: 'Penny Stocks' },
]

function fmtVol(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function fmtCap(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n <= 0) return '-'
  return fmtVol(n)
}

function fmtPct(n: number): string {
  const sign = n >= 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

function pctClass(n: number): string {
  return n >= 0
    ? 'text-emerald-600 dark:text-emerald-400'
    : 'text-red-600 dark:text-red-400'
}

function MoverRow({ mover, rank }: { mover: MoverItem; rank: number }) {
  return (
    <tr className="bg-white dark:bg-zinc-900/40">
      <td className="px-3 py-2 font-bold tabular-nums text-zinc-400">{rank}</td>
      <td className="px-3 py-2">
        <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100">
          {mover.symbol}
        </span>
      </td>
      <td className="px-3 py-2 max-w-[180px] truncate text-zinc-500 dark:text-zinc-400">
        {mover.name}
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-zinc-900 dark:text-zinc-100">
        {mover.price.toFixed(2)}
      </td>
      <td className={`px-3 py-2 text-right tabular-nums font-semibold ${pctClass(mover.change_pct)}`}>
        {fmtPct(mover.change_pct)}
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-zinc-500 dark:text-zinc-400">
        {fmtVol(mover.volume)}
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-zinc-500 dark:text-zinc-400">
        {fmtCap(mover.market_cap)}
      </td>
    </tr>
  )
}

export default function MarketMoversExplorer() {
  const [market, setMarket] = useState<Market>('usa')
  const [category, setCategory] = useState<MoverCategory>('gainers')
  const { data, loading, error } = useMoversExplorer(market, category)

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">
            Market Movers
          </h2>
          <p className="text-[10px] font-mono text-zinc-500">
            TradingView scanner: gainers, losers, most active and penny stocks across markets
          </p>
        </div>

        <label className="flex items-center gap-2 text-xs font-semibold text-zinc-500">
          Market
          <select
            aria-label="Market"
            value={market}
            onChange={(e) => setMarket(e.target.value as Market)}
            className="rounded-lg border border-zinc-300 bg-white px-2 py-1.5 text-xs font-semibold text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          >
            {MARKETS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div
        role="tablist"
        aria-label="Mover category"
        className="inline-flex flex-wrap rounded-xl bg-zinc-100 p-1 dark:bg-zinc-900"
      >
        {CATEGORIES.map(({ value, label }) => {
          const active = category === value
          return (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setCategory(value)}
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

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-900" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load market movers.</p>
      ) : !data || data.movers.length === 0 ? (
        <p className="text-sm text-zinc-500">No movers found for this market and category.</p>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-zinc-200 dark:border-zinc-800">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="bg-zinc-50 text-[10px] font-semibold uppercase tracking-wider text-zinc-500 dark:bg-zinc-900/70">
              <tr>
                <th className="px-3 py-2">#</th>
                <th className="px-3 py-2">Symbol</th>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2 text-right">Price</th>
                <th className="px-3 py-2 text-right">Change</th>
                <th className="px-3 py-2 text-right">Volume</th>
                <th className="px-3 py-2 text-right">Mkt Cap</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
              {data.movers.map((m, i) => (
                <MoverRow key={m.symbol} mover={m} rank={i + 1} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[11px] text-zinc-400 dark:text-zinc-500">
        Sourced from the TradingView scanner API, filtered to instruments with market cap over
        $100M (penny stocks below $5 are exempt from the cap filter). Bonds and futures scanners
        are not covered yet.
      </p>
    </div>
  )
}
