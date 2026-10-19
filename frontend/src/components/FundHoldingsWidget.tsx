import { useState } from 'react'
import { useFundHoldings } from '../hooks/useFundHoldings'
import type { Fund, FundConsensus, FundPosition } from '../types'
import type { PortfolioTickerLookup } from '../hooks/usePortfolioTickers'
import { PortfolioTickerBadge } from './PortfolioTickerBadge'
import { compactMoney as money } from '../utils/compactMoney'

const BADGE_BASE = 'rounded-full px-2 py-0.5 text-[11px] font-semibold'
const BADGE_BUY = 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
const BADGE_SELL = 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
const BADGE_NEUTRAL = 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
const BADGE_WARN = 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'

const INSTRUMENT: Record<string, string> = { call: 'Calls', put: 'Puts', note: 'Notes' }

function fmtQuarter(value: string | null): string {
  if (!value) return '—'
  const d = new Date(`${value}T00:00:00Z`)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })
}

function label(row: { ticker: string | null; issuer: string | null }): string {
  return row.ticker ?? row.issuer ?? '—'
}

function actionBadge(row: FundPosition): { label: string; className: string } {
  switch (row.action) {
    case 'new':
      return { label: 'New', className: BADGE_BUY }
    case 'sold_out':
      return { label: 'Sold out', className: BADGE_SELL }
    case 'added':
      return { label: `+${(row.shares_change_pct ?? 0).toFixed(0)}%`, className: BADGE_BUY }
    case 'reduced':
      return { label: `${(row.shares_change_pct ?? 0).toFixed(0)}%`, className: BADGE_SELL }
    default:
      return { label: 'Held', className: BADGE_NEUTRAL }
  }
}

function Consensus({
  title,
  hint,
  rows,
  className,
  portfolioLookup,
}: {
  title: string
  hint: string
  rows: FundConsensus[]
  className: string
  portfolioLookup?: PortfolioTickerLookup
}) {
  return (
    <div className="min-w-0 flex-1">
      <p className="mb-1 text-[11px] uppercase tracking-wide text-zinc-500" title={hint}>
        {title}
      </p>
      {rows.length === 0 ? (
        <p className="text-xs text-zinc-500">Nothing yet.</p>
      ) : (
        <div className="flex flex-wrap gap-1">
          {rows.slice(0, 10).map((row) => (
            <span
              key={row.cusip}
              title={`${row.issuer ?? ''}: ${row.funds.join(', ')}`}
              className={`${BADGE_BASE} ${className} inline-flex items-center gap-1`}
            >
              {row.ticker ? `$${row.ticker}` : row.issuer}
              <span className="font-normal opacity-75">{row.funds.length}</span>
              {row.ticker && <PortfolioTickerBadge status={portfolioLookup?.(row.ticker) ?? null} />}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function ChangeList({
  title,
  rows,
  portfolioLookup,
}: {
  title: string
  rows: FundPosition[]
  portfolioLookup?: PortfolioTickerLookup
}) {
  return (
    <div className="min-w-0">
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{title}</p>
      {rows.length === 0 ? (
        <p className="text-xs text-zinc-500">No changes.</p>
      ) : (
        <ul className="space-y-1">
          {rows.map((row) => {
            const badge = actionBadge(row)
            return (
              <li key={`${row.cusip}-${row.instrument ?? ''}`} className="flex items-center justify-between gap-2 text-xs">
                <span className="flex min-w-0 items-center gap-1" title={row.issuer ?? undefined}>
                  <span className="truncate font-semibold text-zinc-800 dark:text-zinc-200">{label(row)}</span>
                  {row.instrument && <span className="text-[10px] text-zinc-500">{INSTRUMENT[row.instrument]}</span>}
                  {row.ticker && <PortfolioTickerBadge status={portfolioLookup?.(row.ticker) ?? null} />}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <span className="font-mono text-zinc-500">{money(row.value_change)}</span>
                  <span className={`${BADGE_BASE} ${badge.className}`}>{badge.label}</span>
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function FundDetail({ fund, portfolioLookup }: { fund: Fund; portfolioLookup?: PortfolioTickerLookup }) {
  const maxWeight = Math.max(...fund.top_holdings.map((h) => h.weight_pct), 1)
  return (
    <section className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900/60">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-100">
            {fund.name}
            {fund.manager && <span className="font-normal text-zinc-500"> · {fund.manager}</span>}
          </h3>
          <p className="text-[11px] text-zinc-500">
            {money(fund.total_value)} in {fund.positions} positions · quarter ending {fmtQuarter(fund.report_date)} ·{' '}
            {fund.new_positions} new, {fund.sold_out} sold out
          </p>
        </div>
        <a href={fund.filing_url} target="_blank" rel="noreferrer" className="text-[11px] text-sky-600 hover:underline dark:text-sky-400">
          SEC filing
        </a>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="min-w-0">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Top holdings</p>
          <ul className="space-y-1">
            {fund.top_holdings.map((row) => {
              const badge = actionBadge(row)
              return (
                <li key={`${row.cusip}-${row.instrument ?? ''}`} className="text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex min-w-0 items-center gap-1" title={row.issuer ?? undefined}>
                      <span className="truncate font-semibold text-zinc-800 dark:text-zinc-200">{label(row)}</span>
                      {row.instrument && <span className="text-[10px] text-zinc-500">{INSTRUMENT[row.instrument]}</span>}
                      {row.ticker && <PortfolioTickerBadge status={portfolioLookup?.(row.ticker) ?? null} />}
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      <span className="font-mono text-zinc-600 dark:text-zinc-300">{row.weight_pct.toFixed(1)}%</span>
                      {row.action !== 'unchanged' && (
                        <span className={`${BADGE_BASE} ${badge.className}`}>{badge.label}</span>
                      )}
                    </span>
                  </div>
                  <div className="mt-0.5 h-1 rounded-full bg-zinc-200 dark:bg-zinc-800">
                    <div className="h-1 rounded-full bg-sky-500" style={{ width: `${(row.weight_pct / maxWeight) * 100}%` }} />
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
        <ChangeList title="Bought" rows={fund.buys} portfolioLookup={portfolioLookup} />
        <ChangeList title="Sold" rows={fund.sells} portfolioLookup={portfolioLookup} />
      </div>
    </section>
  )
}

interface Props {
  portfolioLookup?: PortfolioTickerLookup
}

export default function FundHoldingsWidget({ portfolioLookup }: Props) {
  const { data, loading, error } = useFundHoldings()
  const [selectedCik, setSelectedCik] = useState<number | null>(null)
  const selected = data?.funds.find((f) => f.cik === selectedCik) ?? data?.funds[0]

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Big Investors</h2>
          <p className="text-[11px] text-zinc-500">
            What well-known funds bought and sold, from their quarterly 13F filings
            {data?.report_date ? ` · quarter ending ${fmtQuarter(data.report_date)}` : ''}
          </p>
        </div>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          SEC 13F
        </span>
      </div>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-8 animate-pulse rounded bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-500">Could not load fund holdings.</p>
      ) : !data || !selected ? (
        <p className="text-sm text-zinc-500">No 13F filings available right now.</p>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-col gap-3 lg:flex-row">
            <Consensus
              title="Most bought"
              hint="Stocks the most funds opened or added to last quarter; the number is how many funds"
              rows={data.most_bought}
              className={BADGE_BUY}
              portfolioLookup={portfolioLookup}
            />
            <Consensus
              title="Most sold"
              hint="Stocks the most funds trimmed or sold out of last quarter"
              rows={data.most_sold}
              className={BADGE_SELL}
              portfolioLookup={portfolioLookup}
            />
            <Consensus
              title="Most widely held"
              hint="Stocks held by the most of these funds"
              rows={data.most_held}
              className={BADGE_NEUTRAL}
              portfolioLookup={portfolioLookup}
            />
          </div>

          <div className="flex gap-1 overflow-x-auto pb-1" role="group" aria-label="Pick a fund">
            {data.funds.map((fund) => (
              <button
                key={fund.cik}
                type="button"
                aria-pressed={fund.cik === selected.cik}
                onClick={() => setSelectedCik(fund.cik)}
                title={fund.manager ?? undefined}
                className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                  fund.cik === selected.cik
                    ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                    : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
                }`}
              >
                {fund.name}
                {fund.stale && <span className={`${BADGE_BASE} ${BADGE_WARN} ml-1`}>old</span>}
              </button>
            ))}
          </div>

          <FundDetail fund={selected} portfolioLookup={portfolioLookup} />

          <p className="text-[11px] text-zinc-400">
            13Fs are filed up to 45 days after the quarter ends and list US long positions only: no shorts, cash or
            foreign listings. "Bought" and "Sold" value the change in shares at the quarter-end price; options are the
            value of the underlying shares.
            {data.missing.length > 0 && ` Could not load: ${data.missing.join(', ')}.`}
          </p>
        </div>
      )}
    </div>
  )
}
