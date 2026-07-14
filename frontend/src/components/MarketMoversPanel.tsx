import type { MarketMover } from '../types'
import { useMarketMovers } from '../hooks/useMarketMovers'

function fmtVol(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
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

function sessionBadgeClass(sessionType: string): string {
  if (sessionType === 'pre-market')
    return 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
  if (sessionType === 'after-hours')
    return 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300'
  return 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
}

function MoverRow({ mover, rank }: { mover: MarketMover; rank: number }) {
  return (
    <tr className="border-b border-zinc-100 dark:border-zinc-800 last:border-0">
      <td className="py-1 pr-2 text-xs text-zinc-400 tabular-nums w-5">{rank}</td>
      <td className="py-1 pr-2">
        <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100">
          {mover.symbol}
        </span>
      </td>
      <td className="py-1 pr-2 max-w-[120px] truncate text-xs text-zinc-500 dark:text-zinc-400">
        {mover.name}
      </td>
      <td className="py-1 pr-2 text-xs text-right tabular-nums text-zinc-900 dark:text-zinc-100">
        ${mover.extended_price.toFixed(2)}
      </td>
      <td className={`py-1 pr-2 text-xs text-right tabular-nums font-semibold ${pctClass(mover.change_pct)}`}>
        {fmtPct(mover.change_pct)}
      </td>
      <td className="py-1 text-xs text-right tabular-nums text-zinc-500 dark:text-zinc-400">
        {fmtVol(mover.volume)}
      </td>
    </tr>
  )
}

function MoversTable({
  movers,
  label,
  headerClass,
}: {
  movers: MarketMover[]
  label: string
  headerClass: string
}) {
  return (
    <div className="flex-1 min-w-0">
      <p className={`mb-2 text-xs font-bold uppercase tracking-wide ${headerClass}`}>{label}</p>
      <table className="w-full">
        <tbody>
          {movers.map((m, i) => (
            <MoverRow key={m.symbol} mover={m} rank={i + 1} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function MarketMoversPanel() {
  const { data, loading } = useMarketMovers()

  if (loading || !data) return null

  const isPreMarket = data.session_type === 'pre-market'

  return (
    <div className="mb-4 rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mb-3 flex items-center gap-2">
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${sessionBadgeClass(data.session_type)}`}
        >
          {isPreMarket ? 'Pre-market' : 'After-hours'}
        </span>
        <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          {isPreMarket ? 'Pre-market Movers' : 'After-hours Movers'}
        </span>
        {data.stale === true && (
          <span className="text-xs text-amber-500 dark:text-amber-400">⚠ Stale</span>
        )}
      </div>
      <div className="flex gap-6">
        <MoversTable
          movers={data.gainers}
          label="Gainers"
          headerClass="text-emerald-600 dark:text-emerald-400"
        />
        <MoversTable
          movers={data.losers}
          label="Losers"
          headerClass="text-red-600 dark:text-red-400"
        />
      </div>
    </div>
  )
}
