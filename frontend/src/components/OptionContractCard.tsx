import type { ReactNode } from 'react'
import type { Asset, TweetOptionContract } from '../types'
import { useOptionContract } from '../hooks/useOptionContract'
import { contractLabel } from '../utils/optionContracts'

function fmtPrice(value: number): string {
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtPercent(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

function fmtCompactUsd(value: number): string {
  return `$${new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(value)}`
}

function fmtExpiration(iso: string): string {
  const parsed = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return iso
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function changeClass(value: number): string {
  if (value > 0) return 'text-emerald-600 dark:text-emerald-400'
  if (value < 0) return 'text-rose-600 dark:text-rose-400'
  return 'text-zinc-500 dark:text-zinc-400'
}

/**
 * The ticker widget on /options (issue #216): the contract a tweet names and,
 * when it names a specific one (strike and expiry), that option's current
 * price next to the price the poster mentioned.
 */
export default function OptionContractCard({
  contract,
  asset,
  postedAt,
  onTickerSelect,
}: {
  contract: TweetOptionContract
  asset?: Asset
  postedAt?: string | null
  onTickerSelect?: (ticker: string) => void
}) {
  const { quote, loading, isSpecific } = useOptionContract(contract, postedAt)
  const symbol = contract.symbol.toUpperCase()
  const label = `$${contractLabel(contract)}`
  const isCall = contract.right === 'CALL'
  const optionPrice = quote?.status === 'listed' ? (quote.mid ?? quote.last_price ?? null) : null
  const mentionedPrice = typeof contract.price === 'number' ? contract.price : null
  const sincePost =
    optionPrice !== null && mentionedPrice !== null && mentionedPrice > 0
      ? ((optionPrice - mentionedPrice) / mentionedPrice) * 100
      : null
  const underlyingPrice =
    typeof quote?.underlying_price === 'number'
      ? quote.underlying_price
      : typeof asset?.financials?.price === 'number'
        ? asset.financials.price
        : null
  const underlyingChange =
    typeof asset?.financials?.change_percent === 'number' ? asset.financials.change_percent : null

  let priceLine: ReactNode
  if (!isSpecific) {
    priceLine = <span className="text-zinc-500 dark:text-zinc-400">No strike and expiry named</span>
  } else if (loading) {
    priceLine = <span className="text-zinc-500 dark:text-zinc-400">Loading quote…</span>
  } else if (quote?.status === 'expired') {
    priceLine = <span className="font-semibold text-zinc-500 dark:text-zinc-400">Expired {fmtExpiration(quote.expiration)}</span>
  } else if (optionPrice !== null) {
    priceLine = (
      <>
        <span className="font-semibold text-zinc-900 dark:text-zinc-100" title={quote?.mid ? 'Bid/ask midpoint' : 'Last trade'}>
          {fmtPrice(optionPrice)}
        </span>
        {typeof quote?.change_percent === 'number' && (
          <span className={`font-semibold ${changeClass(quote.change_percent)}`}>{fmtPercent(quote.change_percent)}</span>
        )}
      </>
    )
  } else {
    priceLine = <span className="text-zinc-500 dark:text-zinc-400">No quote for this contract</span>
  }

  const details = [
    quote?.status === 'listed' && quote.expiration ? `Exp ${fmtExpiration(quote.expiration)}` : null,
    typeof quote?.implied_volatility === 'number' ? `IV ${(quote.implied_volatility * 100).toFixed(0)}%` : null,
    typeof quote?.open_interest === 'number' && quote.open_interest > 0 ? `OI ${quote.open_interest.toLocaleString()}` : null,
  ].filter(Boolean)

  return (
    <div
      aria-label={`Option ${contractLabel(contract)}`}
      className="rounded-xl border border-zinc-200 bg-zinc-50/70 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-800/50"
    >
      <div className="flex items-center justify-between gap-2">
        {onTickerSelect ? (
          <button
            type="button"
            onClick={() => onTickerSelect(symbol)}
            aria-label={`Filter by $${symbol}`}
            className="truncate text-left font-semibold text-zinc-800 underline-offset-2 hover:underline dark:text-zinc-100"
          >
            {label}
          </button>
        ) : (
          <div className="truncate font-semibold text-zinc-800 dark:text-zinc-100">{label}</div>
        )}
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
            isCall
              ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
              : 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300'
          }`}
        >
          {isCall ? 'Call' : 'Put'}
        </span>
      </div>

      <div className="truncate text-[11px] text-zinc-500 dark:text-zinc-400">
        {asset?.name && asset.name !== symbol ? `${asset.name} · ` : ''}
        {underlyingPrice !== null ? `$${symbol} ${fmtPrice(underlyingPrice)}` : `$${symbol}`}
        {underlyingChange !== null && (
          <span className={`ml-1 ${changeClass(underlyingChange)}`}>{fmtPercent(underlyingChange)}</span>
        )}
      </div>

      <div className="mt-1 flex items-center justify-between gap-2 text-sm">{priceLine}</div>

      {(mentionedPrice !== null || typeof contract.notional_usd === 'number') && (
        <div className="mt-0.5 flex flex-wrap items-center justify-between gap-x-2 text-[11px] text-zinc-500 dark:text-zinc-400">
          {mentionedPrice !== null && (
            <span>
              Mentioned at <span className="font-medium text-zinc-700 dark:text-zinc-300">{fmtPrice(mentionedPrice)}</span>
              {sincePost !== null && (
                <span className={`ml-1 font-semibold ${changeClass(sincePost)}`}>{fmtPercent(sincePost)} since</span>
              )}
            </span>
          )}
          {typeof contract.notional_usd === 'number' && <span>Premium {fmtCompactUsd(contract.notional_usd)}</span>}
        </div>
      )}

      {details.length > 0 && (
        <div className="mt-0.5 text-[11px] text-zinc-500 dark:text-zinc-400">{details.join(' · ')}</div>
      )}
    </div>
  )
}
