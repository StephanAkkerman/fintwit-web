import { useEffect, useMemo, useState } from 'react'
import {
  Banknote,
  Bitcoin,
  LayoutDashboard,
  LineChart,
  Menu,
  Radar,
  ShieldCheck,
  SlidersHorizontal,
  Trophy,
  Wallet,
  X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import BinanceGainersLosersWidget from './components/BinanceGainersLosersWidget'
import DebugAdminPanel from './components/DebugAdminPanel'
import EarningsCalendarWidget from './components/EarningsCalendarWidget'
import EconomicEventsWidget from './components/EconomicEventsWidget'
import ErrorBoundary from './components/ErrorBoundary'
import ExtendedHoursPanel from './components/ExtendedHoursPanel'
import ForexMacroWidget from './components/ForexMacroWidget'
import MarketMoversPanel from './components/MarketMoversPanel'
import { MentionHeatmap } from './components/MentionHeatmap'
import { OverviewDashboard } from './components/OverviewDashboard'
import { RouteSignalsPanel } from './components/RouteSignalsPanel'
import IbkrPanel from './components/IbkrPanel'
import OptionsOverviewWidget from './components/OptionsOverviewWidget'
import PortfolioAssetInsights from './components/PortfolioAssetInsights'
import PortfolioDiversification from './components/PortfolioDiversification'
import PortfolioPanel from './components/PortfolioPanel'
import PortfolioValueChart from './components/PortfolioValueChart'
import SignaSection from './components/SignaSection'
import SpyHeatmapWidget from './components/SpyHeatmapWidget'
import SectorOverviewWidget from './components/SectorOverviewWidget'
import StockFearGreedWidget from './components/StockFearGreedWidget'
import StockHaltsWidget from './components/StockHaltsWidget'
import StockMarketHoursBanner from './components/StockMarketHoursBanner'
import StocktwitsWidget from './components/StocktwitsWidget'
import TickerDetailModal from './components/TickerDetailModal'
import TraderLeaderboardWidget from './components/TraderLeaderboardWidget'
import TreemapWidget from './components/TreemapWidget'
import TrendingCryptoWidget from './components/TrendingCryptoWidget'
import TweetCard from './components/TweetCard'
import { useIbkr } from './hooks/useIbkr'
import { useTweets } from './hooks/useTweets'
import { useMentionFrequency } from './hooks/useMentionFrequency'
import { usePortfolioTickers } from './hooks/usePortfolioTickers'
import type { AssetKind, Tweet } from './types'
import { hasChartSignal } from './utils/tweetSignals'

type FilterKey = 'all' | 'crypto' | 'stock' | 'forex'
type RouteKey =
  | 'home'
  | 'crypto'
  | 'stocks'
  | 'forex'
  | 'options'
  | 'signa'
  | 'traders'
  | 'portfolio'
  | 'admin'
type ChartSortMode = 'latest' | 'charts-first' | 'charts-only'
type LookbackWindow = 24 | 48 | 168

const LOOKBACK_WINDOWS: Array<{ value: LookbackWindow; label: string }> = [
  { value: 24, label: '24h' },
  { value: 48, label: '48h' },
  { value: 168, label: '7d' },
]

const SECTIONS: Array<{ key: RouteKey; label: string; path: string; subtitle: string; icon: LucideIcon }> = [
  { key: 'home', label: 'Home', path: '/', subtitle: 'Cross-market stream', icon: LayoutDashboard },
  { key: 'crypto', label: 'Crypto', path: '/crypto', subtitle: 'Coins, trend, heatmap', icon: Bitcoin },
  { key: 'stocks', label: 'Stocks', path: '/stocks', subtitle: 'Equity sentiment and SPY map', icon: LineChart },
  { key: 'forex', label: 'Forex', path: '/forex', subtitle: 'Macro events and FX sentiment', icon: Banknote },
  { key: 'options', label: 'Options', path: '/options', subtitle: 'Flow activity and put/call balance', icon: SlidersHorizontal },
  { key: 'signa', label: 'Signa', path: '/signa', subtitle: 'Best trades + live model signals from getsigna.ai', icon: Radar },
  { key: 'traders', label: 'Traders', path: '/traders', subtitle: 'Credibility leaderboard: whose calls actually work out', icon: Trophy },
  { key: 'portfolio', label: 'Portfolio', path: '/portfolio', subtitle: 'Value over time, asset context and PnL', icon: Wallet },
  { key: 'admin', label: 'Admin', path: '/admin', subtitle: 'Debug tweet injection and verification', icon: ShieldCheck },
]

function routeFromPath(pathname: string): RouteKey {
  if (pathname.startsWith('/crypto')) return 'crypto'
  if (pathname.startsWith('/stocks')) return 'stocks'
  if (pathname.startsWith('/forex')) return 'forex'
  if (pathname.startsWith('/options')) return 'options'
  if (pathname.startsWith('/signa')) return 'signa'
  if (pathname.startsWith('/traders')) return 'traders'
  if (pathname.startsWith('/portfolio')) return 'portfolio'
  if (pathname.startsWith('/admin')) return 'admin'
  return 'home'
}

function pathFromRoute(route: RouteKey): string {
  if (route === 'crypto') return '/crypto'
  if (route === 'stocks') return '/stocks'
  if (route === 'forex') return '/forex'
  if (route === 'options') return '/options'
  if (route === 'signa') return '/signa'
  if (route === 'traders') return '/traders'
  if (route === 'portfolio') return '/portfolio'
  if (route === 'admin') return '/admin'
  return '/'
}

function isCryptoKind(kind: string | null | undefined): boolean {
  return (kind ?? '').toUpperCase().includes('CRYPTO')
}

function isForexKind(kind: string | null | undefined, symbol: string): boolean {
  const k = (kind ?? '').toUpperCase()
  const s = symbol.toUpperCase()
  // Explicitly labeled forex or macro-related indices/futures
  return (
    k === 'FOREX' ||
    (k === 'INDEX' && (s === 'DXY' || s === 'EXY' || s === 'BXY' || s === 'JXY' || s === 'USDOLLAR' || s.startsWith('US') || s.startsWith('EU'))) ||
    (k === 'FUTURE' && (s.startsWith('6') || s === 'DX')) // e.g. 6E=F (EUR futures), DX=F (DXY futures)
  )
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

function normalizeUserInput(value: string): string | null {
  const normalized = value.trim().replace(/^@+/, '').toLowerCase()
  if (!normalized) return null
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

function matchesUser(tweet: Tweet, user: string): boolean {
  const target = user.toLowerCase()
  const candidates = [
    tweet.user_name,
    tweet.user_screen_name,
    tweet.quoted_user_name,
    tweet.quoted_user_screen_name,
    tweet.quoted_tweet?.user_name,
    tweet.quoted_tweet?.user_screen_name,
  ]

  return candidates.some((value) => {
    if (!value) return false
    const normalized = value.replace(/^@+/, '').toLowerCase()
    return normalized.includes(target)
  })
}

function matchesFilter(tweet: Tweet, filter: FilterKey): boolean {
  if (filter === 'all') return true

  const assets = tweet.assets ?? []
  const hasFinancialSignals =
    assets.length > 0 ||
    (tweet.tickers?.length ?? 0) > 0 ||
    hasTickerLikeText(tweet.text ?? '')

  if (filter === 'crypto') {
    return assets.some((asset) => isCryptoKind(asset.kind))
  }

  if (filter === 'forex') {
    return assets.some((asset) => isForexKind(asset.kind, asset.symbol))
  }

  // Stock filter (default fallback for other assets or generic financial signals)
  const hasCrypto = assets.some((asset) => isCryptoKind(asset.kind))
  const hasForex = assets.some((asset) => isForexKind(asset.kind, asset.symbol))
  const hasStock =
    assets.some((asset) => !isCryptoKind(asset.kind) && !isForexKind(asset.kind, asset.symbol)) ||
    (assets.length === 0 && hasFinancialSignals && !hasCrypto && !hasForex)

  return hasStock
}

function isSubscriberOnlyTweet(tweet: Tweet): boolean {
  return Boolean(tweet.is_subscriber_only || tweet.quoted_tweet?.is_subscriber_only)
}

export default function App() {
  const [route, setRoute] = useState<RouteKey>(() => routeFromPath(window.location.pathname))
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [lookbackHours, setLookbackHours] = useState<LookbackWindow>(24)
  const {
    tweets,
    hasMore,
    isInitialLoading,
    isLoadingOlder,
    loadOlder,
    lastLoadDurationMs,
    lastLoadedCount,
  } = useTweets('', 2000, 200, route === 'options', lookbackHours) // same-origin API (proxied in dev)
  const { status: ibkrStatus, positions: ibkrPositions, trades: ibkrTrades, account: ibkrAccount, loading: ibkrLoading, error: ibkrError, reload: reloadIbkr } = useIbkr()
  const [tickerFilter, setTickerFilter] = useState<string | null>(null)
  const [tickerInput, setTickerInput] = useState('')
  const [userFilter, setUserFilter] = useState<string | null>(null)
  const [userInput, setUserInput] = useState('')
  const [subscriberOnlyFilter, setSubscriberOnlyFilter] = useState(false)
  const [chartSortMode, setChartSortMode] = useState<ChartSortMode>('latest')
  const [detailTicker, setDetailTicker] = useState<string | null>(null)

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
    setMobileNavOpen(false)
  }

  const effectiveFilter: FilterKey =
    route === 'crypto'
      ? 'crypto'
      : route === 'forex'
        ? 'forex'
        : route === 'stocks' || route === 'portfolio'
          ? 'stock'
          : 'all'

  const mentionHeatAssetKind: AssetKind =
    route === 'crypto'
      ? 'CRYPTO'
      : route === 'forex'
        ? 'FOREX'
        : route === 'stocks' || route === 'portfolio'
          ? 'EQUITY'
          : 'all'

  const activeSection = useMemo(
    () => SECTIONS.find((section) => section.key === route) ?? SECTIONS[0],
    [route]
  )

  const portfolioSymbols = useMemo(
    () => new Set(ibkrPositions.map((p) => p.symbol.toUpperCase())),
    [ibkrPositions]
  )

  const scopedTweets = useMemo(() => {
    let scoped = tweets.filter(
      (tweet) =>
        matchesFilter(tweet, effectiveFilter) &&
        (!userFilter || matchesUser(tweet, userFilter)) &&
        (!subscriberOnlyFilter || isSubscriberOnlyTweet(tweet))
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

    if (route === 'options') {
      scoped = scoped.filter((tweet) => tweet.is_options_tweet === true)
    }

    return scoped
  }, [tweets, effectiveFilter, userFilter, subscriberOnlyFilter, route, portfolioSymbols])

  const displayedTweets = useMemo(() => {
    let scoped = scopedTweets

    if (tickerFilter) {
      scoped = scoped.filter((tweet) => matchesTicker(tweet, tickerFilter))
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
  }, [scopedTweets, tickerFilter, route, chartSortMode])

  const mentionLookup = useMentionFrequency(displayedTweets)
  const portfolioLookup = usePortfolioTickers()

  const onTickerSelect = (ticker: string) => {
    setTickerInput(ticker)
    setTickerFilter((current) => (current === ticker ? null : ticker))
    setDetailTicker(ticker)
  }

  const applyTypedTickerFilter = () => {
    const ticker = normalizeTickerInput(tickerInput)
    if (!ticker) return
    setTickerInput(ticker)
    setTickerFilter(ticker)
  }

  const onUserSelect = (user: string) => {
    const normalized = normalizeUserInput(user)
    if (!normalized) return
    setUserInput(normalized)
    setUserFilter((current) => (current === normalized ? null : normalized))
  }

  const applyTypedUserFilter = () => {
    const user = normalizeUserInput(userInput)
    if (!user) return
    setUserInput(user)
    setUserFilter(user)
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black text-zinc-900 dark:text-zinc-100">
      <main className="mx-auto max-w-6xl p-4">
        <div className="mb-3 flex items-center gap-3 lg:hidden">
          <button
            type="button"
            onClick={() => setMobileNavOpen(true)}
            aria-label="Open navigation menu"
            className="flex items-center gap-2 rounded-xl border border-zinc-200 bg-white px-3 py-2 text-sm font-semibold text-zinc-700 shadow-sm dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200"
          >
            <Menu className="h-4 w-4" aria-hidden="true" />
            Menu
          </button>
          <span className="text-sm font-semibold text-zinc-500 dark:text-zinc-400">{activeSection.label}</span>
        </div>

        {mobileNavOpen && (
          <div
            role="presentation"
            onClick={() => setMobileNavOpen(false)}
            className="fixed inset-0 z-30 bg-black/50 backdrop-blur-sm lg:hidden"
          />
        )}

        <div className="grid gap-4 lg:grid-cols-[15rem_minmax(0,1fr)] lg:items-start">
          <aside
            className={`fixed inset-y-0 left-0 z-40 w-72 max-w-[85vw] overflow-y-auto border-r border-zinc-200 bg-white p-3 shadow-xl transition-transform duration-200 ease-out dark:border-zinc-800 dark:bg-zinc-900 lg:sticky lg:top-4 lg:z-auto lg:h-fit lg:max-h-[calc(100vh-2rem)] lg:w-auto lg:max-w-none lg:translate-x-0 lg:rounded-2xl lg:border lg:bg-white/80 lg:shadow-sm lg:transition-none dark:lg:bg-zinc-900/70 ${
              mobileNavOpen ? 'translate-x-0' : '-translate-x-full'
            }`}
          >
            <div className="flex items-center justify-between px-2">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Sections</h2>
              <button
                type="button"
                onClick={() => setMobileNavOpen(false)}
                aria-label="Close navigation menu"
                className="rounded-lg p-1 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-800 dark:hover:text-zinc-100 lg:hidden"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <div className="mt-2 flex flex-col gap-1">
              {SECTIONS.map((section) => {
                const active = section.key === route
                const Icon = section.icon
                return (
                  <button
                    key={section.key}
                    type="button"
                    onClick={() => navigateTo(section.key)}
                    aria-label={`Open ${section.path}`}
                    className={`flex items-center gap-2.5 rounded-xl px-3 py-2 text-left transition-colors ${
                      active
                        ? 'bg-indigo-600 text-white dark:bg-indigo-500'
                        : 'hover:bg-zinc-100 dark:hover:bg-zinc-800'
                    }`}
                  >
                    <Icon className={`h-4 w-4 shrink-0 ${active ? 'text-white' : 'text-zinc-400'}`} aria-hidden="true" />
                    <div>
                      <div className="text-sm font-semibold">{section.label}</div>
                      <div className={`text-xs ${active ? 'text-white/80' : 'text-zinc-500'}`}>
                        {section.path}
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>

            {route === 'crypto' || route === 'stocks' || route === 'forex' ? (
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
                          ? 'bg-indigo-600 text-white dark:bg-indigo-500'
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
                          ? 'bg-indigo-600 text-white dark:bg-indigo-500'
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
                          ? 'bg-indigo-600 text-white dark:bg-indigo-500'
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
                Options page is auto-filtered to tweets classified as options flow/contract commentary.
              </p>
            ) : route === 'portfolio' ? (
              <p className="mt-4 px-2 text-xs text-zinc-500">
                {portfolioSymbols.size > 0
                  ? `Showing tweets for your ${portfolioSymbols.size} position${portfolioSymbols.size === 1 ? '' : 's'}: ${[...portfolioSymbols].join(', ')}`
                  : 'Timeline will filter to your IBKR positions once connected.'}
              </p>
            ) : (
              <p className="mt-4 px-2 text-xs text-zinc-500">
                Use this route to inject a debug tweet via `/api/debug/tweet` and verify timeline behavior.
              </p>
            )}

            <div className="mt-4 border-t border-zinc-200 pt-3 dark:border-zinc-800">
              <h3 className="px-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                Lookback
              </h3>
              <div className="mt-2 flex flex-wrap gap-1.5 px-2">
                {LOOKBACK_WINDOWS.map((window) => {
                  const active = lookbackHours === window.value
                  return (
                    <button
                      key={window.value}
                      type="button"
                      aria-label={`Lookback ${window.label}`}
                      onClick={() => setLookbackHours(window.value)}
                      className={`rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                        active
                          ? 'bg-indigo-600 text-white dark:bg-indigo-500'
                          : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
                      }`}
                    >
                      {window.label}
                    </button>
                  )
                })}
              </div>
              <div className="mt-2 space-y-1 px-2 text-xs text-zinc-500">
                <p>Current window: last {lookbackHours}h</p>
                <p>Last load: {lastLoadDurationMs === null ? '--' : `${lastLoadDurationMs} ms`}</p>
                <p>Fetched tweets: {lastLoadedCount}</p>
                <p>Loaded in memory: {tweets.length}</p>
                {isInitialLoading && <p className="text-zinc-400">Refreshing timeline...</p>}
              </div>
            </div>

            <div className="mt-4 border-t border-zinc-200 pt-3 dark:border-zinc-800">
              <h3 className="px-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                Access
              </h3>
              <div className="mt-2 px-2">
                <button
                  type="button"
                  aria-pressed={subscriberOnlyFilter}
                  onClick={() => setSubscriberOnlyFilter((current) => !current)}
                  className={`w-full rounded-xl px-3 py-2 text-left text-sm font-semibold transition-colors ${
                    subscriberOnlyFilter
                      ? 'bg-indigo-600 text-white dark:bg-indigo-500'
                      : 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700'
                  }`}
                >
                  Subscriber-only tweets
                </button>
                <p className="mt-2 text-xs text-zinc-500">
                  {subscriberOnlyFilter
                    ? 'Showing only tweets marked as subscriber-only, including quoted subscriber-only posts.'
                    : 'Toggle this to focus the timeline on subscriber-only posts.'}
                </p>
              </div>
            </div>

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
                  className="min-w-0 flex-1 rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm text-zinc-900 outline-none ring-indigo-400 placeholder:text-zinc-400 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                />
                <button
                  type="submit"
                  className="rounded-lg bg-indigo-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 dark:bg-indigo-500 dark:hover:bg-indigo-400"
                >
                  Apply
                </button>
              </form>

              {tickerFilter ? (
                <div className="mt-2 flex items-center gap-2 px-2">
                  <span className="rounded-full bg-indigo-600 px-2 py-1 text-xs font-semibold text-white dark:bg-indigo-500">
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

            <div className="mt-4 border-t border-zinc-200 pt-3 dark:border-zinc-800">
              <h3 className="px-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                User
              </h3>
              <form
                className="mt-2 flex items-center gap-2 px-2"
                onSubmit={(ev) => {
                  ev.preventDefault()
                  applyTypedUserFilter()
                }}
              >
                <input
                  id="user-filter-input"
                  type="text"
                  value={userInput}
                  onChange={(ev) => setUserInput(ev.target.value)}
                  placeholder="@trader"
                  aria-label="User name"
                  className="min-w-0 flex-1 rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm text-zinc-900 outline-none ring-indigo-400 placeholder:text-zinc-400 focus:ring-2 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                />
                <button
                  type="submit"
                  className="rounded-lg bg-indigo-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 dark:bg-indigo-500 dark:hover:bg-indigo-400"
                >
                  Apply
                </button>
              </form>

              {userFilter ? (
                <div className="mt-2 flex items-center gap-2 px-2">
                  <span className="rounded-full bg-indigo-600 px-2 py-1 text-xs font-semibold text-white dark:bg-indigo-500">
                    @{userFilter}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setUserFilter(null)
                      setUserInput('')
                    }}
                    className="text-xs text-zinc-500 hover:underline"
                  >
                    Clear
                  </button>
                </div>
              ) : (
                <p className="mt-2 px-2 text-xs text-zinc-500">Type a user name or click a tweet author to filter.</p>
              )}
            </div>
          </aside>

          <section className="space-y-3 min-w-0">
            <header className="sticky top-0 z-10 bg-inherit/60 backdrop-blur p-2 -mx-2">
              <h1 className="text-2xl font-bold">X Stream</h1>
              <p className="text-sm text-zinc-500">{activeSection.subtitle}</p>
            </header>

            {route !== 'admin' && route !== 'signa' && route !== 'home' && route !== 'traders' && (
              <>
                <ErrorBoundary label="Mention heat">
                  <MentionHeatmap
                    assetKind={mentionHeatAssetKind}
                    onTickerClick={onTickerSelect}
                    userFilter={userFilter}
                    subscriberOnly={subscriberOnlyFilter}
                    height={220}
                  />
                </ErrorBoundary>
                <ErrorBoundary label="More signals">
                  <RouteSignalsPanel
                    assetKind={mentionHeatAssetKind}
                    userFilter={userFilter}
                    subscriberOnly={subscriberOnlyFilter}
                  />
                </ErrorBoundary>
              </>
            )}

            {route === 'home' && (
              <ErrorBoundary label="Market overview">
                <OverviewDashboard
                  onTickerClick={onTickerSelect}
                  userFilter={userFilter}
                  subscriberOnly={subscriberOnlyFilter}
                  portfolioLookup={portfolioLookup}
                />
              </ErrorBoundary>
            )}

            {route === 'crypto' && (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <ErrorBoundary label="Binance movers">
                  <BinanceGainersLosersWidget />
                </ErrorBoundary>
                <ErrorBoundary label="Trending crypto">
                  <TrendingCryptoWidget />
                </ErrorBoundary>
                <div className="sm:col-span-2">
                  <ErrorBoundary label="Crypto treemap">
                    <TreemapWidget />
                  </ErrorBoundary>
                </div>
              </div>
            )}

            {route === 'stocks' && (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <ErrorBoundary label="Fear & Greed index">
                  <StockFearGreedWidget />
                </ErrorBoundary>
                <ErrorBoundary label="Trading halts">
                  <StockHaltsWidget />
                </ErrorBoundary>
                <div className="sm:col-span-2">
                  <ErrorBoundary label="Market hours">
                    <StockMarketHoursBanner />
                  </ErrorBoundary>
                </div>
                <ErrorBoundary label="StockTwits">
                  <StocktwitsWidget />
                </ErrorBoundary>
                <div className="sm:col-span-2">
                  <ErrorBoundary label="Market movers">
                    <MarketMoversPanel />
                  </ErrorBoundary>
                </div>
                <div className="sm:col-span-2">
                  <ErrorBoundary label="Extended hours">
                    <ExtendedHoursPanel />
                  </ErrorBoundary>
                </div>
                <div className="sm:col-span-2">
                  <ErrorBoundary label="Market heatmap">
                    <SpyHeatmapWidget />
                  </ErrorBoundary>
                </div>
                <div className="sm:col-span-2">
                  <ErrorBoundary label="Sector overview">
                    <SectorOverviewWidget />
                  </ErrorBoundary>
                </div>
                <div className="sm:col-span-2">
                  <ErrorBoundary label="Earnings calendar">
                    <EarningsCalendarWidget portfolioLookup={portfolioLookup} />
                  </ErrorBoundary>
                </div>
              </div>
            )}

            {route === 'forex' && (
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                <ErrorBoundary label="Macro snapshot">
                  <ForexMacroWidget />
                </ErrorBoundary>
                <ErrorBoundary label="Economic events">
                  <EconomicEventsWidget />
                </ErrorBoundary>
              </div>
            )}

            {route === 'options' && (
              <ErrorBoundary label="Options overview">
                <OptionsOverviewWidget />
              </ErrorBoundary>
            )}

            {route === 'signa' && (
              <ErrorBoundary label="Signa">
                <SignaSection />
              </ErrorBoundary>
            )}

            {route === 'traders' && (
              <ErrorBoundary label="Trader credibility">
                <TraderLeaderboardWidget />
              </ErrorBoundary>
            )}

            {route === 'portfolio' && (
              <>
                <ErrorBoundary label="Portfolio value">
                  <PortfolioValueChart />
                </ErrorBoundary>
                <ErrorBoundary label="Asset context">
                  <PortfolioAssetInsights />
                </ErrorBoundary>
                <ErrorBoundary label="Portfolio balance and sectors">
                  <PortfolioDiversification />
                </ErrorBoundary>
                <ErrorBoundary label="IBKR live positions">
                  <IbkrPanel
                    status={ibkrStatus}
                    positions={ibkrPositions}
                    trades={ibkrTrades}
                    account={ibkrAccount}
                    loading={ibkrLoading}
                    error={ibkrError}
                    reload={reloadIbkr}
                  />
                </ErrorBoundary>
                <ErrorBoundary label="Portfolio positions">
                  <PortfolioPanel />
                </ErrorBoundary>
              </>
            )}

            {route === 'admin' && (
              <ErrorBoundary label="Debug admin">
                <DebugAdminPanel />
              </ErrorBoundary>
            )}

            {route !== 'signa' && route !== 'traders' && (
              <>
                {displayedTweets.map((t) => (
                  // Per card: tweet payloads vary with upstream, and one
                  // malformed post should cost its own card, not the timeline.
                  <ErrorBoundary key={t.id} label="This tweet" compact>
                    <TweetCard
                      t={t}
                      onTickerSelect={onTickerSelect}
                      onUserSelect={onUserSelect}
                      mentionLookup={mentionLookup}
                      portfolioLookup={portfolioLookup}
                    />
                  </ErrorBoundary>
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
              </>
            )}
          </section>
        </div>
      </main>
      {detailTicker && (
        <TickerDetailModal ticker={detailTicker} onClose={() => setDetailTicker(null)} />
      )}
    </div>
  )
}
