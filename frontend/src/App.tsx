import { useEffect, useMemo, useState } from 'react'
import BinanceGainersLosersWidget from './components/BinanceGainersLosersWidget'
import DebugAdminPanel from './components/DebugAdminPanel'
import EconomicEventsWidget from './components/EconomicEventsWidget'
import FearGreedWidget from './components/FearGreedWidget'
import IbkrPanel from './components/IbkrPanel'
import MarketOverview from './components/MarketOverview'
import NftTrendingWidget from './components/NftTrendingWidget'
import OptionsOverviewWidget from './components/OptionsOverviewWidget'
import RedditWsbWidget from './components/RedditWsbWidget'
import SpyHeatmapWidget from './components/SpyHeatmapWidget'
import StockHaltsWidget from './components/StockHaltsWidget'
import StockMarketHoursBanner from './components/StockMarketHoursBanner'
import StocktwitsWidget from './components/StocktwitsWidget'
import TreemapWidget from './components/TreemapWidget'
import TrendingCryptoWidget from './components/TrendingCryptoWidget'
import TweetCard from './components/TweetCard'
import { useIbkr } from './hooks/useIbkr'
import { useTweets } from './hooks/useTweets'
import type { Tweet } from './types'
import { hasChartSignal } from './utils/tweetSignals'

type FilterKey = 'all' | 'crypto' | 'stock' | 'non-financial'
type RouteKey = 'home' | 'crypto' | 'stocks' | 'forex' | 'options' | 'nfts' | 'portfolio' | 'admin'
type ChartSortMode = 'latest' | 'charts-first' | 'charts-only'

const SECTIONS: Array<{ key: RouteKey; label: string; path: string; subtitle: string }> = [
  { key: 'home', label: 'Home', path: '/', subtitle: 'Cross-market stream' },
  { key: 'crypto', label: 'Crypto', path: '/crypto', subtitle: 'Coins, trend, heatmap' },
  { key: 'stocks', label: 'Stocks', path: '/stocks', subtitle: 'Equity sentiment and SPY map' },
  { key: 'forex', label: 'Forex', path: '/forex', subtitle: 'Macro events and FX sentiment' },
  { key: 'options', label: 'Options', path: '/options', subtitle: 'Flow activity and put/call balance' },
  { key: 'nfts', label: 'NFTs', path: '/nfts', subtitle: 'Collection momentum and floor-price pulse' },
  { key: 'portfolio', label: 'Portfolio', path: '/portfolio', subtitle: 'IBKR stock positions and PnL' },
  { key: 'admin', label: 'Admin', path: '/admin', subtitle: 'Debug tweet injection and verification' },
]

const FILTERS: Array<{ key: FilterKey; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'crypto', label: 'Crypto' },
  { key: 'stock', label: 'Stock' },
  { key: 'non-financial', label: 'Non-financial' },
]

function routeFromPath(pathname: string): RouteKey {
  if (pathname.startsWith('/crypto')) return 'crypto'
  if (pathname.startsWith('/stocks')) return 'stocks'
  if (pathname.startsWith('/forex')) return 'forex'
  if (pathname.startsWith('/options')) return 'options'
  if (pathname.startsWith('/nfts')) return 'nfts'
  if (pathname.startsWith('/portfolio')) return 'portfolio'
  if (pathname.startsWith('/admin')) return 'admin'
  return 'home'
}

function pathFromRoute(route: RouteKey): string {
  if (route === 'crypto') return '/crypto'
  if (route === 'stocks') return '/stocks'
  if (route === 'forex') return '/forex'
  if (route === 'options') return '/options'
  if (route === 'nfts') return '/nfts'
  if (route === 'portfolio') return '/portfolio'
  if (route === 'admin') return '/admin'
  return '/'
}

function isCryptoKind(kind: string | null | undefined): boolean {
  return (kind ?? '').toUpperCase().includes('CRYPTO')
}

function hasTickerLikeText(text: string): boolean {
  return /(^|\s)\$[A-Za-z][A-Za-z0-9]{0,9}\b/.test(text)
}

function extractTickersFromText(text: string): string[] {
  return [...text.matchAll(/(^|\s)\$([A-Za-z][A-Za-z0-9]{0,9})\b/g)].map((m) =>
    m[2].toUpperCase()
  )
}

function normalizeTickerInput(value: string): string | null {
  const normalized = value.trim().replace(/^\$/, '').toUpperCase()
  if (!/^[A-Z][A-Z0-9]{0,9}$/.test(normalized)) return null
  return normalized
}

function matchesTicker(tweet: Tweet, ticker: string): boolean {
  const target = ticker.toUpperCase()
  const fromTickers = (tweet.tickers ?? []).map((t) => t.toUpperCase())
  const fromAssets = (tweet.assets ?? []).map((asset) => asset.symbol.toUpperCase())
  const fromText = extractTickersFromText(tweet.text ?? '')
  const fromHashtags = (tweet.hashtags ?? []).map((h) => h.toUpperCase())
  return [...fromTickers, ...fromAssets, ...fromText, ...fromHashtags].includes(target)
}

function matchesFilter(tweet: Tweet, filter: FilterKey): boolean {
  if (filter === 'all') return true

  const assets = tweet.assets ?? []
  const hasFinancialSignals =
    assets.length > 0 ||
    (tweet.tickers?.length ?? 0) > 0 ||
    hasTickerLikeText(tweet.text ?? '')
  const hasCrypto = assets.some((asset) => isCryptoKind(asset.kind))
  const hasStock =
    assets.some((asset) => !isCryptoKind(asset.kind)) ||
    (assets.length === 0 && hasFinancialSignals)

  if (filter === 'crypto') return hasCrypto
  if (filter === 'stock') return hasStock
  return !hasFinancialSignals
}

export default function App() {
  const { tweets, hasMore, isLoadingOlder, loadOlder } = useTweets('') // same-origin API (proxied in dev)
  const { status: ibkrStatus, positions: ibkrPositions, trades: ibkrTrades, account: ibkrAccount, loading: ibkrLoading, error: ibkrError, reload: reloadIbkr } = useIbkr()
  const [route, setRoute] = useState<RouteKey>(() => routeFromPath(window.location.pathname))
  const [activeFilter, setActiveFilter] = useState<FilterKey>('all')
  const [tickerFilter, setTickerFilter] = useState<string | null>(null)
  const [tickerInput, setTickerInput] = useState('')
  const [chartSortMode, setChartSortMode] = useState<ChartSortMode>('latest')

  useEffect(() => {
    const onPopState = () => {
      setRoute(routeFromPath(window.location.pathname))
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const navigateTo = (nextRoute: RouteKey) => {
    const path = pathFromRoute(nextRoute)
    if (window.location.pathname !== path) {
      window.history.pushState({}, '', path)
    }
    setRoute(nextRoute)
  }

  const effectiveFilter: FilterKey =
    route === 'crypto'
      ? 'crypto'
      : route === 'stocks' || route === 'forex' || route === 'options' || route === 'portfolio'
        ? 'stock'
        : activeFilter

  const activeSection = useMemo(
    () => SECTIONS.find((section) => section.key === route) ?? SECTIONS[0],
    [route]
  )

  const counts = useMemo(
    () => ({
      all: tweets.length,
      crypto: tweets.filter((tweet) => matchesFilter(tweet, 'crypto')).length,
      stock: tweets.filter((tweet) => matchesFilter(tweet, 'stock')).length,
      'non-financial': tweets.filter((tweet) => matchesFilter(tweet, 'non-financial')).length,
    }),
    [tweets]
  )

  const portfolioSymbols = useMemo(
    () => new Set(ibkrPositions.map((p) => p.symbol.toUpperCase())),
    [ibkrPositions]
  )

  const displayedTweets = useMemo(() => {
    let scoped = tweets.filter(
      (tweet) =>
        matchesFilter(tweet, effectiveFilter) &&
        (!tickerFilter || matchesTicker(tweet, tickerFilter))
    )

    if (route === 'portfolio' && portfolioSymbols.size > 0) {
      scoped = scoped.filter((tweet) => {
        const symbols = [
          ...(tweet.tickers ?? []).map((t) => t.toUpperCase()),
          ...(tweet.assets ?? []).map((a) => a.symbol.toUpperCase()),
          ...extractTickersFromText(tweet.text ?? ''),
        ]
        return symbols.some((s) => portfolioSymbols.has(s))
      })
    }

    if (route !== 'crypto' && route !== 'stocks' && route !== 'forex') {
      return scoped
    }

    if (chartSortMode === 'charts-only') {
      return scoped.filter(hasChartSignal)
    }

    if (chartSortMode === 'charts-first') {
      return [...scoped].sort((a, b) => Number(hasChartSignal(b)) - Number(hasChartSignal(a)))
    }

    return scoped
  }, [tweets, effectiveFilter, tickerFilter, route, chartSortMode, portfolioSymbols])

  const onTickerSelect = (ticker: string) => {
    setActiveFilter('all')
    setTickerInput(ticker)
    setTickerFilter((current) => (current === ticker ? null : ticker))
  }

  const applyTypedTickerFilter = () => {
    const ticker = normalizeTickerInput(tickerInput)
    if (!ticker) return
    setActiveFilter('all')
    setTickerInput(ticker)
    setTickerFilter(ticker)
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black text-zinc-900 dark:text-zinc-100">
      <main className="mx-auto max-w-6xl p-4">
        <div className="grid gap-4 lg:grid-cols-[15rem_minmax(0,1fr)]">
          <aside className="h-fit rounded-2xl border border-zinc-200 bg-white/80 p-3 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/70 lg:sticky lg:top-4">
            <h2 className="px-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">Sections</h2>
            <div className="mt-2 flex flex-col gap-1">
              {SECTIONS.map((section) => {
                const active = section.key === route
                return (
                  <button
                    key={section.key}
                    type="button"
                    onClick={() => navigateTo(section.key)}
                    aria-label={`Open ${section.path}`}
                    className={`rounded-xl px-3 py-2 text-left transition-colors ${
                      active
                        ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                        : 'hover:bg-zinc-100 dark:hover:bg-zinc-800'
                    }`}
                  >
                    <div className="text-sm font-semibold">{section.label}</div>
                    <div className={`text-xs ${active ? 'text-white/80 dark:text-zinc-700' : 'text-zinc-500'}`}>
                      {section.path}
                    </div>
                  </button>
                )
              })}
            </div>

            {route === 'home' ? (
              <>
                <h2 className="mt-4 px-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">Filters</h2>
                <div className="mt-2 flex flex-col gap-1">
                  {FILTERS.map((filter) => {
                    const active = filter.key === activeFilter
                    return (
                      <button
                        key={filter.key}
                        type="button"
                        onClick={() => setActiveFilter(filter.key)}
                        aria-label={`Timeline filter ${filter.label}`}
                        className={`flex items-center justify-between rounded-xl px-3 py-2 text-sm transition-colors ${
                          active
                            ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                            : 'hover:bg-zinc-100 dark:hover:bg-zinc-800'
                        }`}
                      >
                        <span>{filter.label}</span>
                        <span className={`rounded-full px-2 py-0.5 text-xs ${active ? 'bg-white/20 dark:bg-black/10' : 'bg-zinc-200 dark:bg-zinc-700'}`}>
                          {counts[filter.key]}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </>
            ) : route === 'crypto' || route === 'stocks' || route === 'forex' ? (
              <>
                <p className="mt-4 px-2 text-xs text-zinc-500">
                  Timeline is auto-filtered to {route === 'crypto' ? 'crypto' : route === 'forex' ? 'macro/forex' : 'stocks'} signals on this page.
                </p>
                <div className="mt-3 px-2">
                  <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">Chart sort</h3>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <button
                      type="button"
                      aria-label="Chart sort Latest"
                      onClick={() => setChartSortMode('latest')}
                      className={`rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                        chartSortMode === 'latest'
                          ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                          : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
                      }`}
                    >
                      Latest
                    </button>
                    <button
                      type="button"
                      aria-label="Chart sort Charts first"
                      onClick={() => setChartSortMode('charts-first')}
                      className={`rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                        chartSortMode === 'charts-first'
                          ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                          : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
                      }`}
                    >
                      Charts first
                    </button>
                    <button
                      type="button"
                      aria-label="Chart sort Charts only"
                      onClick={() => setChartSortMode('charts-only')}
                      className={`rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                        chartSortMode === 'charts-only'
                          ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                          : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
                      }`}
                    >
                      Charts only
                    </button>
                  </div>
                </div>
              </>
            ) : route === 'options' ? (
              <p className="mt-4 px-2 text-xs text-zinc-500">
                Options page is auto-filtered to stock-linked symbols and highlights call/put activity.
              </p>
            ) : route === 'portfolio' ? (
              <p className="mt-4 px-2 text-xs text-zinc-500">
                {portfolioSymbols.size > 0
                  ? `Showing tweets for your ${portfolioSymbols.size} position${portfolioSymbols.size === 1 ? '' : 's'}: ${[...portfolioSymbols].join(', ')}`
                  : 'Timeline will filter to your IBKR positions once connected.'}
              </p>
            ) : route === 'nfts' ? (
              <p className="mt-4 px-2 text-xs text-zinc-500">
                NFTs route highlights trending collections and floor-price momentum from CoinGecko.
              </p>
            ) : (
              <p className="mt-4 px-2 text-xs text-zinc-500">
                Use this route to inject a debug tweet via `/api/debug/tweet` and verify timeline behavior.
              </p>
            )}

            <div className="mt-4 border-t border-zinc-200 pt-3 dark:border-zinc-800">
              <h3 className="px-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                Ticker
              </h3>
              <form
                className="mt-2 flex items-center gap-2 px-2"
                onSubmit={(ev) => {
                  ev.preventDefault()
                  applyTypedTickerFilter()
                }}
              >
                <input
                  id="ticker-filter-input"
                  type="text"
                  value={tickerInput}
                  onChange={(ev) => setTickerInput(ev.target.value)}
                  placeholder="$SOL"
                  aria-label="Ticker symbol"
                  className="min-w-0 flex-1 rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm text-zinc-900 outline-none ring-zinc-400 placeholder:text-zinc-400 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                />
                <button
                  type="submit"
                  className="rounded-lg bg-zinc-900 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
                >
                  Apply
                </button>
              </form>

              {tickerFilter ? (
                <div className="mt-2 flex items-center gap-2 px-2">
                  <span className="rounded-full bg-zinc-900 px-2 py-1 text-xs font-semibold text-white dark:bg-zinc-100 dark:text-zinc-900">
                    ${tickerFilter}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setTickerFilter(null)
                      setTickerInput('')
                    }}
                    className="text-xs text-zinc-500 hover:underline"
                  >
                    Clear
                  </button>
                </div>
              ) : (
                <p className="mt-2 px-2 text-xs text-zinc-500">Type a ticker or click one in a tweet to filter.</p>
              )}
            </div>
          </aside>

          <section className="space-y-3 min-w-0">
            <header className="sticky top-0 z-10 bg-inherit/60 backdrop-blur p-2 -mx-2">
              <h1 className="text-2xl font-bold">X Stream</h1>
              <p className="text-sm text-zinc-500">{activeSection.subtitle}</p>
            </header>

            {route === 'home' && (
              <>
                <FearGreedWidget />
                <RedditWsbWidget />
                <MarketOverview />
              </>
            )}

            {route === 'crypto' && (
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                <BinanceGainersLosersWidget />
                <TrendingCryptoWidget />
                <TreemapWidget />
              </div>
            )}

            {route === 'stocks' && (
              <>
                <StockMarketHoursBanner />
                <StockHaltsWidget />
                <StocktwitsWidget />
                <SpyHeatmapWidget />
              </>
            )}

            {route === 'forex' && <EconomicEventsWidget />}

            {route === 'options' && <OptionsOverviewWidget />}

            {route === 'nfts' && <NftTrendingWidget />}

            {route === 'portfolio' && (
              <IbkrPanel
                status={ibkrStatus}
                positions={ibkrPositions}
                trades={ibkrTrades}
                account={ibkrAccount}
                loading={ibkrLoading}
                error={ibkrError}
                reload={reloadIbkr}
              />
            )}

            {route === 'admin' && <DebugAdminPanel />}

            {displayedTweets.map((t) => (
              <TweetCard key={t.id} t={t} onTickerSelect={onTickerSelect} />
            ))}
            {hasMore && (
              <div className="flex justify-center py-2">
                <button
                  type="button"
                  onClick={() => void loadOlder()}
                  disabled={isLoadingOlder}
                  className="rounded-xl border border-zinc-300 bg-white px-4 py-2 text-sm font-semibold text-zinc-700 transition-colors hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
                >
                  {isLoadingOlder ? 'Loading older tweets...' : 'Load older tweets'}
                </button>
              </div>
            )}
            {displayedTweets.length === 0 && (
              <div className="rounded-2xl border border-dashed border-zinc-300 bg-white/70 p-5 text-sm text-zinc-500 dark:border-zinc-700 dark:bg-zinc-900/60 dark:text-zinc-400">
                No tweets in this filter yet.
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  )
}
