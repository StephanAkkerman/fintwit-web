import { useMemo, useState } from 'react'
import { useCongressTrades } from '../hooks/useCongressTrades'
import type { CongressTickerFlow, CongressTrade } from '../types'
import type { PortfolioTickerLookup } from '../hooks/usePortfolioTickers'
import { PortfolioTickerBadge } from './PortfolioTickerBadge'

const BADGE_BASE = 'rounded-full px-2 py-0.5 text-[11px] font-semibold'
const BADGE_BUY = 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
const BADGE_SELL = 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
const BADGE_OTHER = 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'

const PARTY_DOT: Record<string, string> = {
  D: 'bg-sky-500',
  R: 'bg-rose-500',
  I: 'bg-amber-500',
}

type Side = 'all' | 'buy' | 'sell'

const SIDES: { key: Side; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'buy', label: 'Buys' },
  { key: 'sell', label: 'Sells' },
]

const PAGE_SIZE = 15

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(`${iso}T00:00:00Z`)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

function fmtAmount(trade: CongressTrade): string {
  const { amount_min: min, amount_max: max } = trade
  const short = (v: number) =>
    `$${v.toLocaleString(undefined, { notation: 'compact', maximumFractionDigits: 1 })}`
  if (min != null && max != null) return `${short(min)}–${short(max)}`
  if (min != null) return `${short(min)}+`
  return trade.amount_range ?? '—'
}

function sideBadge(trade: CongressTrade): { label: string; className: string } {
  if (trade.transaction === 'buy') return { label: 'Buy', className: BADGE_BUY }
  if (trade.transaction === 'sell') {
    const partial = trade.transaction_label.toLowerCase().includes('partial')
    return { label: partial ? 'Sell (partial)' : 'Sell', className: BADGE_SELL }
  }
  return { label: trade.transaction_label, className: BADGE_OTHER }
}

function FlowList({
  title,
  flows,
  className,
  onSelect,
}: {
  title: string
  flows: CongressTickerFlow[]
  className: string
  onSelect: (ticker: string) => void
}) {
  return (
    <div className="min-w-0 flex-1">
      <p className="mb-1 text-[11px] uppercase tracking-wide text-zinc-500">{title}</p>
      {flows.length === 0 ? (
        <p className="text-xs text-zinc-500">None in this window.</p>
      ) : (
        <div className="flex flex-wrap gap-1">
          {flows.map((flow) => (
            <button
              key={flow.ticker}
              type="button"
              onClick={() => onSelect(flow.ticker)}
              title={flow.politicians.join(', ')}
              className={`${BADGE_BASE} ${className} hover:opacity-80`}
            >
              ${flow.ticker}
              <span className="ml-1 font-normal opacity-75">
                {flow.politicians.length > 1 ? `${flow.politicians.length} members` : `×${flow.trades}`}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

interface Props {
  portfolioLookup?: PortfolioTickerLookup
}

export default function CongressTradesWidget({ portfolioLookup }: Props) {
  const { data, loading, error } = useCongressTrades()
  const [side, setSide] = useState<Side>('all')
  const [politician, setPolitician] = useState('')
  const [ticker, setTicker] = useState<string | null>(null)
  const [shown, setShown] = useState(PAGE_SIZE)

  // Every member in the data, most active first, so the picker isn't limited
  // to the summary's top list.
  const members = useMemo(() => {
    const counts = new Map<string, number>()
    for (const trade of data?.trades ?? []) {
      counts.set(trade.politician, (counts.get(trade.politician) ?? 0) + 1)
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  }, [data?.trades])

  const filtered = useMemo(
    () =>
      (data?.trades ?? []).filter(
        (trade) =>
          (side === 'all' || trade.transaction === side) &&
          (!politician || trade.politician === politician) &&
          (!ticker || trade.ticker === ticker),
      ),
    [data?.trades, side, politician, ticker],
  )

  function resetPaging() {
    setShown(PAGE_SIZE)
  }

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Congress Trades</h2>
          <p className="text-[11px] text-zinc-500">
            STOCK Act disclosures, filed up to 45 days after the trade
            {data?.as_of ? ` · latest filing ${fmtDate(data.as_of)}` : ''}
          </p>
        </div>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          {data && data.summary.trades > 0
            ? `${data.summary.buys} buys · ${data.summary.sells} sells`
            : 'QUIVER'}
        </span>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-8 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load congress trades.</p>
      ) : !data || data.trades.length === 0 ? (
        <p className="text-sm text-zinc-500">No congressional trade disclosures available right now.</p>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-col gap-3 sm:flex-row">
            <FlowList
              title="Most bought"
              flows={data.summary.most_bought}
              className={BADGE_BUY}
              onSelect={(t) => {
                setTicker(t)
                setSide('buy')
                resetPaging()
              }}
            />
            <FlowList
              title="Most sold"
              flows={data.summary.most_sold}
              className={BADGE_SELL}
              onSelect={(t) => {
                setTicker(t)
                setSide('sell')
                resetPaging()
              }}
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex gap-1" role="group" aria-label="Filter by side">
              {SIDES.map((s) => (
                <button
                  key={s.key}
                  type="button"
                  aria-pressed={side === s.key}
                  onClick={() => {
                    setSide(s.key)
                    resetPaging()
                  }}
                  className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                    side === s.key
                      ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                      : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
            <select
              aria-label="Filter by member"
              value={politician}
              onChange={(e) => {
                setPolitician(e.target.value)
                resetPaging()
              }}
              className="rounded-md border border-zinc-200 bg-white px-2 py-1 text-xs text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
            >
              <option value="">All members</option>
              {members.map(([name, count]) => (
                <option key={name} value={name}>
                  {name} ({count})
                </option>
              ))}
            </select>
            {ticker && (
              <button
                type="button"
                onClick={() => {
                  setTicker(null)
                  resetPaging()
                }}
                className={`${BADGE_BASE} ${BADGE_OTHER}`}
                aria-label={`Clear ${ticker} filter`}
              >
                ${ticker} ✕
              </button>
            )}
          </div>

          {filtered.length === 0 ? (
            <p className="text-sm text-zinc-500">No trades match these filters.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs sm:text-sm">
                <thead className="border-b border-zinc-200 text-zinc-500 dark:border-zinc-800">
                  <tr>
                    <th className="py-2">Member</th>
                    <th className="py-2">Stock</th>
                    <th className="py-2">Trade</th>
                    <th className="py-2 text-right">Amount</th>
                    <th className="py-2 text-right">Traded</th>
                    <th className="py-2 text-right">Filed</th>
                    <th className="py-2 text-right" title="Quiver's estimate of the stock's move since the trade, minus the market's">
                      Excess ret.
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.slice(0, shown).map((trade, i) => {
                    const badge = sideBadge(trade)
                    return (
                      <tr
                        key={trade.id ?? `${trade.politician}-${trade.ticker}-${trade.traded}-${i}`}
                        className="border-b border-zinc-100 dark:border-zinc-900/80"
                      >
                        <td className="py-2">
                          <span className="flex items-center gap-1.5">
                            <span
                              className={`inline-block h-2 w-2 shrink-0 rounded-full ${PARTY_DOT[trade.party ?? ''] ?? 'bg-zinc-400'}`}
                              title={trade.party_name ?? undefined}
                            />
                            {trade.website ? (
                              <a href={trade.website} target="_blank" rel="noreferrer" className="hover:underline">
                                {trade.politician}
                              </a>
                            ) : (
                              trade.politician
                            )}
                          </span>
                          <span className="text-[11px] text-zinc-500">
                            {[trade.party, trade.chamber].filter(Boolean).join(' · ')}
                          </span>
                        </td>
                        <td className="py-2" title={trade.asset ?? undefined}>
                          <span className="flex items-center gap-1 font-semibold">
                            {trade.ticker ?? '—'}
                            {trade.ticker && (
                              <PortfolioTickerBadge status={portfolioLookup?.(trade.ticker) ?? null} />
                            )}
                          </span>
                        </td>
                        <td className="py-2">
                          <span className={`${BADGE_BASE} ${badge.className}`}>{badge.label}</span>
                        </td>
                        <td className="py-2 text-right font-mono text-zinc-600 dark:text-zinc-300">
                          {fmtAmount(trade)}
                        </td>
                        <td className="py-2 text-right text-zinc-600 dark:text-zinc-300">{fmtDate(trade.traded)}</td>
                        <td className="py-2 text-right text-zinc-500">{fmtDate(trade.filed)}</td>
                        <td
                          className={`py-2 text-right font-mono ${
                            trade.excess_return_pct == null
                              ? 'text-zinc-500'
                              : trade.excess_return_pct >= 0
                                ? 'text-emerald-600 dark:text-emerald-400'
                                : 'text-rose-600 dark:text-rose-400'
                          }`}
                        >
                          {trade.excess_return_pct == null
                            ? '—'
                            : `${trade.excess_return_pct > 0 ? '+' : ''}${trade.excess_return_pct.toFixed(1)}%`}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              {filtered.length > shown && (
                <button
                  type="button"
                  onClick={() => setShown((n) => n + PAGE_SIZE)}
                  className="mt-2 text-xs font-semibold text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
                >
                  Show more ({filtered.length - shown} left)
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
