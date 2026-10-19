import { useMemo, useState } from 'react'
import { useInsiderTrades } from '../hooks/useInsiderTrades'
import type { InsiderTickerGroup, InsiderTrade } from '../types'
import type { PortfolioTickerLookup } from '../hooks/usePortfolioTickers'
import { PortfolioTickerBadge } from './PortfolioTickerBadge'
import { compactMoney as money } from '../utils/compactMoney'

const BADGE_BASE = 'rounded-full px-2 py-0.5 text-[11px] font-semibold'
const BADGE_BUY = 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
const BADGE_SELL = 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
const BADGE_OTHER = 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'

type Side = 'all' | 'buy' | 'sell'

const SIDES: { key: Side; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'buy', label: 'Buys' },
  { key: 'sell', label: 'Sales' },
]

const PAGE_SIZE = 15

function fmtDate(value: string | null): string {
  if (!value) return '—'
  const d = new Date(`${value.slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

function GroupList({
  title,
  hint,
  groups,
  className,
  showInsiders,
  onSelect,
}: {
  title: string
  hint: string
  groups: InsiderTickerGroup[]
  className: string
  showInsiders: boolean
  onSelect: (ticker: string) => void
}) {
  return (
    <div className="min-w-0 flex-1">
      <p className="mb-1 text-[11px] uppercase tracking-wide text-zinc-500" title={hint}>
        {title}
      </p>
      {groups.length === 0 ? (
        <p className="text-xs text-zinc-500">None in this window.</p>
      ) : (
        <div className="flex flex-wrap gap-1">
          {groups.map((group) => (
            <button
              key={group.ticker}
              type="button"
              onClick={() => onSelect(group.ticker)}
              title={`${group.company ?? group.ticker}: ${group.insiders.join(', ')}`}
              className={`${BADGE_BASE} ${className} hover:opacity-80`}
            >
              ${group.ticker}
              <span className="ml-1 font-normal opacity-75">
                {showInsiders ? `${group.insiders.length} insiders · ` : ''}
                {money(group.value)}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function role(trade: InsiderTrade): string {
  return trade.title ?? (trade.is_ten_percent_owner ? '10% owner' : 'Insider')
}

interface Props {
  portfolioLookup?: PortfolioTickerLookup
}

export default function InsiderTradesWidget({ portfolioLookup }: Props) {
  const { data, loading, error } = useInsiderTrades()
  const [side, setSide] = useState<Side>('buy')
  const [ticker, setTicker] = useState<string | null>(null)
  const [officersOnly, setOfficersOnly] = useState(false)
  const [shown, setShown] = useState(PAGE_SIZE)

  const filtered = useMemo(
    () =>
      (data?.trades ?? []).filter(
        (trade) =>
          (side === 'all' || trade.side === side) &&
          (!ticker || trade.ticker === ticker) &&
          (!officersOnly || trade.is_officer),
      ),
    [data?.trades, side, ticker, officersOnly],
  )

  function select(next: string, nextSide: Side) {
    setTicker(next)
    setSide(nextSide)
    setShown(PAGE_SIZE)
  }

  const summary = data?.summary
  const buyShare = summary?.buy_share_pct

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Insider Trades</h2>
          <p className="text-[11px] text-zinc-500">
            Open-market buys and sales of $25k+ by officers, directors and 10% owners (SEC Form 4), filed in the last{' '}
            {data?.filter.days ?? 30} days{data?.as_of ? ` · latest filing ${fmtDate(data.as_of)}` : ''}
          </p>
        </div>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          {summary ? `${summary.buys} buys · ${summary.sells} sales` : 'SEC FORM 4'}
        </span>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-8 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load insider trades.</p>
      ) : !data || !summary || data.trades.length === 0 ? (
        <p className="text-sm text-zinc-500">No insider trades available right now.</p>
      ) : (
        <div className="space-y-3">
          <div>
            <div className="flex justify-between text-[11px] text-zinc-500">
              <span className="text-emerald-600 dark:text-emerald-400">Bought {money(summary.buy_value)}</span>
              <span className="text-rose-600 dark:text-rose-400">Sold {money(summary.sell_value)}</span>
            </div>
            <div
              className="mt-1 flex h-2 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800"
              aria-label={buyShare == null ? 'No trades' : `${buyShare.toFixed(0)}% of the dollar value was buying`}
            >
              <span className="bg-emerald-500" style={{ width: `${buyShare ?? 0}%` }} />
              <span className="flex-1 bg-rose-500" />
            </div>
            <p className="mt-1 text-[11px] text-zinc-500">
              Insiders sell far more often than they buy (pay, taxes, diversification), so a rising buy share matters
              more than the level.
            </p>
          </div>

          <div className="flex flex-col gap-3 lg:flex-row">
            <GroupList
              title="Cluster buys"
              hint="Two or more insiders buying the same stock in this window"
              groups={summary.cluster_buys}
              className={BADGE_BUY}
              showInsiders
              onSelect={(t) => select(t, 'buy')}
            />
            <GroupList
              title="Biggest buys"
              hint="Largest total purchases per stock"
              groups={summary.top_buys}
              className={BADGE_BUY}
              showInsiders={false}
              onSelect={(t) => select(t, 'buy')}
            />
            <GroupList
              title="Biggest sales"
              hint="Largest total sales per stock, leaving out sales tied to an option exercise"
              groups={summary.top_sells}
              className={BADGE_SELL}
              showInsiders={false}
              onSelect={(t) => select(t, 'sell')}
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
                    setShown(PAGE_SIZE)
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
            <label className="flex items-center gap-1 text-[11px] text-zinc-600 dark:text-zinc-300">
              <input
                type="checkbox"
                checked={officersOnly}
                onChange={(e) => {
                  setOfficersOnly(e.target.checked)
                  setShown(PAGE_SIZE)
                }}
              />
              CEO, CFO, COO, president or chair only
            </label>
            {ticker && (
              <button
                type="button"
                onClick={() => {
                  setTicker(null)
                  setShown(PAGE_SIZE)
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
                    <th className="py-2">Stock</th>
                    <th className="py-2">Insider</th>
                    <th className="py-2">Trade</th>
                    <th className="py-2 text-right">Value</th>
                    <th className="py-2 text-right">Price</th>
                    <th className="py-2 text-right" title="Change in the insider's holding">
                      Stake
                    </th>
                    <th className="py-2 text-right">Traded</th>
                    <th className="py-2 text-right">Filed</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.slice(0, shown).map((trade, i) => (
                    <tr
                      key={`${trade.filing_url ?? trade.ticker}-${trade.insider}-${trade.traded}-${i}`}
                      className="border-b border-zinc-100 dark:border-zinc-900/80"
                    >
                      <td className="py-2" title={trade.company ?? undefined}>
                        <span className="flex items-center gap-1 font-semibold">
                          {trade.ticker}
                          <PortfolioTickerBadge status={portfolioLookup?.(trade.ticker) ?? null} />
                        </span>
                        {trade.company && (
                          <span className="block max-w-[10rem] truncate text-[11px] font-normal text-zinc-500">
                            {trade.company}
                          </span>
                        )}
                      </td>
                      <td className="py-2">
                        <span className="block">{trade.insider ?? '—'}</span>
                        <span className="text-[11px] text-zinc-500">{role(trade)}</span>
                      </td>
                      <td className="py-2">
                        <span className={`${BADGE_BASE} ${trade.side === 'buy' ? BADGE_BUY : BADGE_SELL}`}>
                          {trade.side === 'buy' ? 'Buy' : trade.with_option_exercise ? 'Sale + exercise' : 'Sale'}
                        </span>
                      </td>
                      <td className="py-2 text-right font-mono text-zinc-700 dark:text-zinc-200">
                        {trade.filing_url ? (
                          <a href={trade.filing_url} target="_blank" rel="noreferrer" className="hover:underline">
                            {money(trade.value)}
                          </a>
                        ) : (
                          money(trade.value)
                        )}
                      </td>
                      <td className="py-2 text-right font-mono text-zinc-600 dark:text-zinc-300">
                        {trade.price == null ? '—' : `$${trade.price.toFixed(2)}`}
                      </td>
                      <td className="py-2 text-right font-mono text-zinc-600 dark:text-zinc-300">
                        {trade.new_position
                          ? 'New'
                          : trade.owned_change_pct == null
                            ? '—'
                            : `${trade.owned_change_pct > 0 ? '+' : ''}${trade.owned_change_pct.toFixed(0)}%`}
                      </td>
                      <td className="py-2 text-right text-zinc-600 dark:text-zinc-300">{fmtDate(trade.traded)}</td>
                      <td className="py-2 text-right text-zinc-500">{fmtDate(trade.filed_at)}</td>
                    </tr>
                  ))}
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
          <p className="text-[11px] text-zinc-400">
            Parsed from SEC filings by OpenInsider; the value links to the Form 4. Sales right after an option exercise
            are usually pay being cashed out.
          </p>
        </div>
      )}
    </div>
  )
}
