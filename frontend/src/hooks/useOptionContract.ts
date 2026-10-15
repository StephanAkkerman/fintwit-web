import { useEffect, useState } from 'react'
import type { OptionContractQuote, TweetOptionContract } from '../types'

// Several cards on /options often name the same contract; share one request.
const cache = new Map<string, Promise<OptionContractQuote | null>>()

function fetchQuote(params: URLSearchParams): Promise<OptionContractQuote | null> {
  const key = params.toString()
  let pending = cache.get(key)
  if (!pending) {
    pending = fetch(`/api/options/contract?${key}`)
      .then((res) => (res.ok ? (res.json() as Promise<OptionContractQuote>) : null))
      .catch(() => null)
    // Drop failures so a later render can retry.
    pending.then((quote) => {
      if (quote === null) cache.delete(key)
    })
    cache.set(key, pending)
  }
  return pending
}

/**
 * Quote for a contract a tweet names, when it names a specific one (ticker,
 * call/put, strike and expiry). `postedAt` resolves year-less expiries.
 */
export function useOptionContract(contract: TweetOptionContract, postedAt?: string | null) {
  const [quote, setQuote] = useState<OptionContractQuote | null>(null)
  const [loading, setLoading] = useState(false)

  const isSpecific =
    Boolean(contract.symbol) && typeof contract.strike === 'number' && Boolean(contract.expiry)
  const asOf = postedAt ? postedAt.slice(0, 10) : ''

  useEffect(() => {
    if (!isSpecific) {
      setQuote(null)
      setLoading(false)
      return
    }
    const params = new URLSearchParams({
      symbol: contract.symbol,
      right: contract.right,
      strike: String(contract.strike),
      expiry: String(contract.expiry),
    })
    if (/^\d{4}-\d{2}-\d{2}$/.test(asOf)) params.set('as_of', asOf)

    let active = true
    setLoading(true)
    void fetchQuote(params).then((result) => {
      if (!active) return
      setQuote(result)
      setLoading(false)
    })
    return () => {
      active = false
    }
  }, [isSpecific, contract.symbol, contract.right, contract.strike, contract.expiry, asOf])

  return { quote, loading, isSpecific }
}
