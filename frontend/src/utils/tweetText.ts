// X writes some crypto cashtags as "smart" tags: the post shows "$BTC" but the
// API text says "bitcoin:native" (issue #216). The backend rewrites new posts;
// this covers posts stored before it did. Keep in sync with
// _NATIVE_COIN_SYMBOLS in app/runtime/symbols.py.
const NATIVE_COIN_SYMBOLS: Record<string, string> = {
  bitcoin: 'BTC',
  ethereum: 'ETH',
  solana: 'SOL',
  ripple: 'XRP',
  xrp: 'XRP',
  dogecoin: 'DOGE',
  cardano: 'ADA',
  binancecoin: 'BNB',
  bnb: 'BNB',
  tron: 'TRX',
  avalanche: 'AVAX',
  polkadot: 'DOT',
  litecoin: 'LTC',
  polygon: 'POL',
  near: 'NEAR',
  sui: 'SUI',
  aptos: 'APT',
  toncoin: 'TON',
  ton: 'TON',
  stellar: 'XLM',
  cosmos: 'ATOM',
  hyperliquid: 'HYPE',
  monero: 'XMR',
}

const SMART_CASHTAG_RE = /(?<![\w$])\$?([a-z0-9]+(?:-[a-z0-9]+)*):native\b/gi

/** Rewrite "bitcoin:native" to "$BTC"; unknown slugs fall back to the tweet's one unwritten ticker. */
export function normalizeSmartCashtags(text: string, tickers: string[] = []): string {
  if (!/:native\b/i.test(text)) return text
  const written = new Set([...text.matchAll(/(?<!\w)\$([a-z][a-z0-9]{0,9})\b/gi)].map((m) => m[1].toUpperCase()))
  const unmatched = [...new Set(tickers.map((t) => t.toUpperCase()))].filter((t) => !written.has(t))
  return text.replace(SMART_CASHTAG_RE, (_, slug: string) => {
    const symbol = NATIVE_COIN_SYMBOLS[slug.toLowerCase()] ?? (unmatched.length === 1 ? unmatched[0] : slug.toUpperCase())
    return `$${symbol}`
  })
}

// "@handle", but not inside an existing markdown link ("[@handle](...)"), a
// URL path or an email address.
const MENTION_RE = /(?<![\w[/@.])@([A-Za-z0-9_]{1,15})\b(?!\]\()/g

/** Turn @mentions into markdown links to the X profile. */
export function linkifyMentions(text: string): string {
  return text.replace(MENTION_RE, (_, handle: string) => `[@${handle}](https://x.com/${handle})`)
}
