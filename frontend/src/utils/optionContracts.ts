import type { Tweet, TweetOptionContract } from '../types'

const SYMBOL_RE = /^[A-Z][A-Z0-9.]{0,9}$/

/**
 * A contract on a real underlying with at least one detail of the trade.
 * Mirrors is_specific_contract in app/runtime/options_intent.py so posts
 * stored before that filter existed drop off /options too (issue #216).
 */
export function isSpecificContract(contract: TweetOptionContract, tickers: Set<string>): boolean {
  const symbol = String(contract.symbol ?? '').toUpperCase()
  if (!SYMBOL_RE.test(symbol)) return false
  if (contract.right !== 'CALL' && contract.right !== 'PUT') return false
  const hasStrike = typeof contract.strike === 'number'
  const hasDetail =
    hasStrike ||
    Boolean(contract.expiry) ||
    typeof contract.notional_usd === 'number' ||
    typeof contract.price === 'number'
  return hasDetail && (hasStrike || tickers.has(symbol))
}

function tweetTickers(tweet: Tweet): Set<string> {
  const fromText = [tweet.text ?? '', tweet.quoted_tweet?.text ?? ''].flatMap((text) =>
    [...text.matchAll(/(?<!\w)\$([a-z][a-z0-9]{0,9})\b/gi)].map((m) => m[1]),
  )
  return new Set(
    [...(tweet.tickers ?? []), ...(tweet.assets ?? []).map((a) => a.symbol), ...fromText].map((s) =>
      String(s).toUpperCase(),
    ),
  )
}

export function specificContracts(tweet: Tweet): TweetOptionContract[] {
  const contracts = tweet.options_context?.contracts ?? []
  if (contracts.length === 0) return []
  const tickers = tweetTickers(tweet)
  return contracts.filter((c) => isSpecificContract(c, tickers))
}

/** Whether a tweet belongs on /options: classified as options and naming a ticker. */
export function isOptionsTimelineTweet(tweet: Tweet): boolean {
  return tweet.is_options_tweet === true && specificContracts(tweet).length > 0
}

/** One contract per symbol/right/strike/expiry, in the order the tweet names them. */
export function uniqueContracts(contracts: TweetOptionContract[]): TweetOptionContract[] {
  const seen = new Set<string>()
  return contracts.filter((c) => {
    const key = [c.symbol.toUpperCase(), c.right, c.strike ?? '', c.expiry ?? ''].join('|')
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

export function formatStrike(strike: number): string {
  return Number.isInteger(strike) ? String(strike) : strike.toFixed(2).replace(/0$/, '')
}

/** "AAPL 350C 11/06/2026" */
export function contractLabel(contract: TweetOptionContract): string {
  const right = contract.right === 'CALL' ? 'C' : contract.right === 'PUT' ? 'P' : ''
  const strike = typeof contract.strike === 'number' ? `${formatStrike(contract.strike)}${right}` : contract.right
  return [contract.symbol.toUpperCase(), strike, contract.expiry ?? ''].filter(Boolean).join(' ')
}
