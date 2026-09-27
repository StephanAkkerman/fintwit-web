export type AccessAllowlist = { emails: string[] };

export type MediaItem = { url: string; type: string };

export type AssetTradingViewSummary = {
  interval?: 'four_h' | 'one_d' | string | null;
  recommendation: string;
  buy: number;
  neutral: number;
  sell: number;
  summary: string;
};

export type AssetTechnicalAnalysis = {
  source?: string | null;
  website?: string | null;
  symbol?: string | null;
  exchange?: string | null;
  screener?: string | null;
  four_h?: AssetTradingViewSummary | null;
  one_d?: AssetTradingViewSummary | null;
};

export type AssetSignaSignal = {
  source?: string | null;
  symbol?: string | null;
  signal: string;
  score?: number | null;
  trend?: string | null;
  confidence?: number | null;
  timeframe?: string | null;
  website?: string | null;
};

export type AssetStocktwitsSentiment = {
  source?: string | null;
  symbol?: string | null;
  bullish_percent?: number | null;
  bearish_percent?: number | null;
  message_volume?: number | null;
  as_of?: string | null;
  website?: string | null;
};

export type AssetFinancials = {
  price?: number | null;
  change_percent?: number | null;
  volume?: number | null;
  website?: string | null;
  source?: string | null;
  session?: 'regular' | 'pre-market' | 'after-hours' | 'closed' | string | null;
  extended_price?: number | null;
  extended_change_percent?: number | null;
  technical_analysis?: AssetTechnicalAnalysis | null;
  signa?: AssetSignaSignal | null;
  stocktwits_sentiment?: AssetStocktwitsSentiment | null;
  // Today's intraday series (5-min closes) captured when the tweet was
  // enriched; absent when it couldn't be fetched. Not live-refreshed.
  sparkline?: number[] | null;
};

/**
 * Slow-moving valuation/volume metrics from Yahoo's quote. Every field is
 * optional: only what Yahoo actually reported is present, so a missing field
 * means "unknown", never zero.
 */
export type AssetFundamentals = {
  market_cap?: number | null;
  forward_pe?: number | null;
  trailing_pe?: number | null;
  eps_forward?: number | null;
  eps_trailing?: number | null;
  nav?: number | null; // net asset value per share; funds and ETFs only
  day_volume?: number | null; // today's regular-session volume, in shares
  avg_volume?: number | null; // 3-month average daily volume, in shares
  avg_volume_10d?: number | null; // 10-day average daily volume, in shares
  currency?: string | null;
};

export type AssetCompanyProfile = {
  industry_group?: string | null;
  country?: string | null;
  exchange?: string | null;
  currency?: string | null;
  website?: string | null;
  market_cap_category?: string | null;
};

export type Asset = {
  symbol: string;
  kind?: string | null;
  name?: string | null;
  market_cap?: number | null;
  sector?: string | null;
  industry?: string | null;
  company_profile?: AssetCompanyProfile | null;
  fundamentals?: AssetFundamentals | null;
  meta?: unknown;
  financials?: AssetFinancials | null;
};

export type QuotedTweet = {
  id: number | string;
  text: string;
  user_name: string;
  user_screen_name: string;
  user_img: string;
  url: string;
  media: MediaItem[];
  tickers: string[];
  hashtags: string[];
  title: string;
  media_types: string[];
  created_at: string;
  likes: number;
  retweets: number;
  replies: number;
  views: number;
  is_subscriber_only?: boolean;
};

export type TweetOptionContract = {
  symbol: string;
  right: 'CALL' | 'PUT' | string;
  strike?: number | null;
  expiry?: string | null;
  notional_usd?: number | null;
  source?: string | null;
};

export type TweetOptionsContext = {
  classification: 'OPTIONS' | 'SPOT_OR_OTHER' | string;
  score: number;
  confidence: 'low' | 'medium' | 'high' | string;
  side: 'CALL' | 'PUT' | 'MIXED' | 'UNKNOWN' | string;
  contract_count: number;
  contracts: TweetOptionContract[];
  keyword_hits: string[];
  cashtags: string[];
};

/**
 * OCR-derived data from a chart screenshot, populated only when the tweet's
 * image was classified as a chart and its text didn't already mention a
 * ticker. Every field is optional: only what OCR actually found is present.
 */
export type ChartExtraction = {
  symbol?: string | null;
  exchange?: string | null;
  timeframe?: string | null;
  price?: number | null;
  session?: 'regular' | 'pre' | 'post' | string | null;
};

export type Tweet = {
  id: number;
  text: string;
  user_name: string;
  user_screen_name: string;
  user_img: string;
  url: string;
  created_at: string;
  is_subscriber_only?: boolean;
  is_options_tweet?: boolean;
  options_context?: TweetOptionsContext | null;
  media: MediaItem[];
  tickers: string[];
  hashtags: string[];
  title: string;
  media_types: string[];
  replies: number;
  likes: number;
  views: number;
  retweets: number;
  sentiment_label?: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | string | null;
  sentiment_emoji?: string | null;
  sentiment_score?: number | null;
  quoted_user_name?: string | null;
  quoted_user_screen_name?: string | null;
  quoted_user_img?: string | null;
  quoted_url?: string | null;
  quoted_created_at?: string | null;
  quoted_tweet?: QuotedTweet | null;
  quoted_sentiment_label?: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | string | null;
  quoted_sentiment_emoji?: string | null;
  quoted_sentiment_score?: number | null;
  // Signed sentiment per ticker, present only for the tickers a tweet says
  // something different about than `sentiment_score` ("long $NVDA, short
  // $INTC"). Read it through a fallback to `sentiment_score`.
  ticker_sentiment?: Record<string, number> | null;
  has_chart?: boolean | null;
  chart_extraction?: ChartExtraction | null;
  // OCR'd text off a non-chart photo, for tweets whose own text named no
  // ticker (issue #88). Opt-in backend feature (IMAGE_OCR_ENABLED); null
  // when disabled, no photo, or nothing recognized.
  image_text?: string | null;
  assets?: Asset[];
};

export type SignaBestTrade = {
  source?: string | null;
  symbol: string;
  direction?: 'BULLISH' | 'BEARISH' | string | null;
  grade?: string | null;
  alert_tier?: number | null;
  composite_score?: number | null;
  confidence?: number | null; // 0–1
  model_count?: number | null;
  regime?: string | null;
  categories?: string[];
  reason?: string | null;
  key_drivers?: string[];
  model_ids?: string[];
  generated_at?: string | null;
  website?: string | null;
};

export type SignaLiveSignal = {
  source?: string | null;
  id?: string | null;
  symbol: string;
  signal?: string | null; // BUY / SELL / SHORT (directional only)
  direction?: 'BULLISH' | 'BEARISH' | string | null;
  model_id?: string | null;
  model_name?: string | null;
  model_source?: string | null;
  category?: string | null;
  confidence?: number | null; // 0–1
  reason?: string | null;
  entry_price?: number | null;
  stop_level?: number | null;
  target_price?: number | null;
  position_size_pct?: number | null;
  grade?: string | null;
  tier?: number | null;
  score?: number | null;
  conflict_detected?: boolean | null;
  created_at?: string | null;
  website?: string | null;
};

// Trader credibility scoring: a "call" is a non-neutral-sentiment tweet
// mentioning a ticker, graded against the ticker's price at fixed horizons
// after the call (1/7/30 days) since a tweet's holding-period intent isn't
// known.
export type TraderCallHorizon = 1 | 7 | 30;

export type TraderLeaderboardEntry = {
  user_screen_name: string;
  horizon_days: TraderCallHorizon;
  graded_calls: number;
  correct_calls: number;
  hit_rate: number; // 0–1
  avg_return_pct: number | null;
};

export type TraderCallResult = {
  horizon_days: TraderCallHorizon;
  price_at_horizon: number;
  return_pct: number;
  correct: boolean;
  evaluated_at: string;
};

export type TraderCall = {
  id: number;
  tweet_id: number;
  ticker: string;
  direction: 'bullish' | 'bearish';
  sentiment_score: number | null;
  asset_kind: string | null;
  price_at_call: number;
  called_at: string;
  results: TraderCallResult[];
};

export type TraderHorizonStat = {
  horizon_days: TraderCallHorizon;
  graded_calls: number;
  correct_calls: number;
  hit_rate: number | null;
  avg_return_pct: number | null;
};

export type TraderDetail = {
  user_screen_name: string;
  horizons: TraderHorizonStat[];
  recent_calls: TraderCall[];
};

export type TreemapCoin = {
  n: string; // name
  s: string; // symbol
  p: number; // price
  ch: number; // change
  mc: number; // market cap
  v: number; // volume
};

export type TreemapData = {
  data: TreemapCoin[];
  // other fields are omitted since they are not needed
};

export type StocktwitsKeyword = 'ts' | 'm_day' | 'wl_ct_day';

export type StocktwitsItem = {
  stock_id?: number | string;
  symbol: string;
  name: string;
  price: string;
  val: string;
};

export type BinanceMoverItem = {
  symbol: string;
  price_change_percent: number;
  price: number;
  volume: number;
  website: string;
};

export type BinanceGainersLosers = {
  gainers: BinanceMoverItem[];
  losers: BinanceMoverItem[];
};

export type StockHaltItem = {
  Time: string;
  'Issue Symbol': string;
  'Resumption Time'?: string;
};

export type StockFearGreedData = {
  value: number;
  status: string;
  change?: string | null;
};

export type OptionContractActivity = {
  symbol: string;
  contract_type: 'CALL' | 'PUT' | string;
  expiry_date?: string | null;
  strike?: number | null;
  last?: number | null;
  change_percent?: number | null;
  volume: number;
  open_interest: number;
  website?: string | null;
};

export type OptionSymbolOverview = {
  symbol: string;
  asset_class: string;
  as_of?: string | null;
  call_volume: number;
  put_volume: number;
  total_volume: number;
  put_call_ratio?: number | null;
  bullish_minus_bearish: number;
  top_call?: OptionContractActivity | null;
  top_put?: OptionContractActivity | null;
};

export type OptionsOverviewResponse = {
  symbols: OptionSymbolOverview[];
  totals: {
    call_volume: number;
    put_volume: number;
    total_volume: number;
    put_call_ratio?: number | null;
  };
  bullish: Array<{
    symbol: string;
    call_volume: number;
    put_volume: number;
    bullish_minus_bearish: number;
  }>;
  bearish: Array<{
    symbol: string;
    call_volume: number;
    put_volume: number;
    bullish_minus_bearish: number;
  }>;
  most_active_contracts: OptionContractActivity[];
  source: string;
};

export type OptionsChainContract = {
  option_type: 'CALL' | 'PUT' | string;
  strike: number | null;
  bid: number | null;
  ask: number | null;
  last_price: number | null;
  volume: number;
  open_interest: number;
  implied_volatility: number | null;
  change_percent: number | null;
  in_the_money: boolean;
};

export type OptionsChainUnderlying = {
  name?: string | null;
  last_price?: number | null;
  change?: number | null;
  change_percent?: number | null;
  market_cap?: number | null;
  year_high?: number | null;
  year_low?: number | null;
  volume?: number | null;
};

export type OptionsChainResponse = {
  symbol: string;
  underlying: OptionsChainUnderlying;
  expirations: string[];
  expiration: string;
  contracts: OptionsChainContract[];
  source: string;
};

export type GammaRegime = 'positive' | 'negative';

export type GammaStrikePoint = {
  strike: number;
  net_gamma: number;
};

export type GammaExposureSnapshot = {
  symbol: string;
  spot_price: number;
  net_gex: number;
  call_gex: number;
  put_gex: number;
  flip_point: number | null;
  regime: GammaRegime;
  expirations_used: string[];
  by_strike: GammaStrikePoint[];
  as_of: string;
  source: string;
};

export type GammaExposureHistoryPoint = {
  id: number;
  symbol: string;
  captured_at: string;
  spot_price: number;
  net_gex: number;
  call_gex: number | null;
  put_gex: number | null;
  flip_point: number | null;
  regime: GammaRegime;
};

export type GammaExposureHistory = {
  symbol: string;
  days: number;
  points: GammaExposureHistoryPoint[];
};

export type CompanyNewsArticle = {
  symbols: string[];
  title: string;
  excerpt?: string | null;
  url: string;
  date: string;
  source?: string | null;
  /** FinTwitBERT read of headline + excerpt; null when the model is not loaded. */
  sentiment_label?: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | null;
  /** Signed confidence: +1 confidently bullish, -1 confidently bearish. */
  sentiment_score?: number | null;
};

export type CompanyNewsSentimentSummary = {
  /** Articles that received a score. 0 when the sentiment model is unavailable. */
  analyzed: number;
  bullish: number;
  neutral: number;
  bearish: number;
  mean_score: number | null;
  label: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | null;
};

export type CompanyNewsResponse = {
  articles: CompanyNewsArticle[];
  sentiment: CompanyNewsSentimentSummary;
  source: string;
};

export type SpyHeatmapDateRange =
  | 'one_day'
  | 'after_hours'
  | 'yesterday'
  | 'one_week'
  | 'one_month'
  | 'ytd'
  | 'one_year';

export type SpyHeatmapItem = {
  ticker: string;
  sector?: string | null;
  industry?: string | null;
  close?: number | string | null;
  prev_close?: number | string | null;
  marketcap?: number | string | null;
};

export type SectorSubsectorPerformance = {
  industry: string;
  market_cap: number;
  change_percent: number | null;
  stock_count: number;
};

export type SectorPerformance = {
  sector: string;
  market_cap: number;
  change_percent: number | null;
  stock_count: number;
  subsectors: SectorSubsectorPerformance[];
};

export type SectorOverviewResponse = {
  sectors: SectorPerformance[];
};

export type SectorRotationTimeframe = 'daily' | 'weekly';

export type SectorRotationQuadrant = 'leading' | 'weakening' | 'lagging' | 'improving';

export type SectorRotationPoint = {
  date: string;
  rs_ratio: number;
  rs_momentum: number;
};

export type SectorRotationSeries = {
  sector: string;
  etf: string;
  quadrant: SectorRotationQuadrant;
  trail: SectorRotationPoint[];
};

export type SectorRotationResponse = {
  timeframe: SectorRotationTimeframe;
  benchmark: string;
  window: number;
  sectors: SectorRotationSeries[];
};

export type PortfolioPosition = {
  id: number;
  broker: 'IBKR';
  symbol: string;
  quantity: number;
  avg_cost: number;
  currency: string;
  opened_at?: string | null;
  notes?: string | null;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
};

export type PortfolioSummaryPosition = PortfolioPosition & {
  market_price?: number | null;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  unrealized_pnl_percent: number;
  website?: string | null;
};

export type PortfolioSummary = {
  totals: {
    positions: number;
    market_value: number;
    cost_basis: number;
    unrealized_pnl: number;
    unrealized_pnl_percent: number;
  };
  positions: PortfolioSummaryPosition[];
};

export type PortfolioHoldingSource = 'auto' | 'manual' | 'ibkr';

export type PortfolioHistoryRange = '1W' | '1M' | '3M' | '6M' | 'YTD' | '1Y' | '5Y' | 'MAX';

export type PortfolioHistoryPoint = {
  t: string;
  value: number;
  cost_basis: number;
  pnl: number;
  pnl_percent: number;
  /** Where the point came from: a stored snapshot, price reconstruction, or the live quote. */
  source: 'snapshot' | 'reconstructed' | 'live';
};

export type PortfolioHistory = {
  source: PortfolioHoldingSource;
  range: PortfolioHistoryRange;
  available_ranges: PortfolioHistoryRange[];
  holdings: string[];
  totals?: PortfolioTotals;
  points: PortfolioHistoryPoint[];
  cost_basis: number;
  start_value: number | null;
  end_value: number | null;
  change: number | null;
  change_percent: number | null;
  missing_symbols: string[];
};

export type PortfolioTotals = {
  positions: number;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  unrealized_pnl_percent: number;
};

export type PortfolioExtreme = {
  value: number;
  date: string;
};

export type PortfolioFlagTone = 'bullish' | 'bearish' | 'neutral';

export type PortfolioAssetFlag = {
  code:
    | 'at_ath'
    | 'near_ath'
    | 'recent_ath'
    | 'at_atl'
    | 'near_atl'
    | 'recent_atl'
    | 'near_52w_high'
    | 'near_52w_low';
  label: string;
  tone: PortfolioFlagTone;
};

export type PortfolioAssetStats = {
  symbol: string;
  price: number | null;
  last_close: number | null;
  history_start: string | null;
  all_time_high: PortfolioExtreme | null;
  all_time_low: PortfolioExtreme | null;
  week_52_high: PortfolioExtreme | null;
  week_52_low: PortfolioExtreme | null;
  from_ath_percent: number | null;
  from_atl_percent: number | null;
  from_52w_high_percent: number | null;
  from_52w_low_percent: number | null;
  range_position_52w: number | null;
  days_since_ath: number | null;
  days_since_atl: number | null;
  flags: PortfolioAssetFlag[];
};

export type PortfolioInsightPosition = {
  symbol: string;
  quantity: number;
  avg_cost: number;
  cost_basis: number;
  currency: string;
  market_price: number | null;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_percent: number;
  change_percent: number | null;
  weight_percent: number;
  website?: string | null;
  stats: PortfolioAssetStats | null;
};

export type PortfolioHighlight = PortfolioAssetFlag & {
  symbol: string;
  weight_percent: number | null;
};

export type PortfolioSector = {
  sector: string;
  market_value: number;
  weight_percent: number;
  symbols: string[];
};

export type PortfolioConcentration = {
  symbol: string;
  weight_percent: number;
};

export type PortfolioSectorConcentration = {
  sector: string;
  weight_percent: number;
};

export type PortfolioDiversificationLabel =
  | 'unrated'
  | 'concentrated'
  | 'moderate'
  | 'diversified';

export type PortfolioDiversification = {
  label: PortfolioDiversificationLabel;
  tone: PortfolioFlagTone;
  holding_hhi: number | null;
  effective_holdings: number | null;
  sector_hhi: number | null;
  effective_sectors: number | null;
  top_holding: PortfolioConcentration | null;
  top_sector: PortfolioSectorConcentration | null;
};

export type PortfolioInsights = {
  source: PortfolioHoldingSource;
  totals: PortfolioTotals;
  positions: PortfolioInsightPosition[];
  highlights: PortfolioHighlight[];
  sectors: PortfolioSector[];
  diversification: PortfolioDiversification;
};

export type RedditPost = {
  id: string;
  subreddit: string;
  title: string;
  description: string;
  author: string;
  score: number;
  num_comments: number;
  created_utc: number;
  url: string;
  image_urls: string[];
};

// Reddit trend analysis (issue #6), from `reddit-stock-analyzer` via
// /api/reddit/trends. Mirrors TickerTrend / TrendReport in that package.
export type RedditTickerTrend = {
  symbol: string;
  rank: number;
  mentions: number;
  previous_mentions: number;
  unique_authors: number;
  engagement: number;
  mentions_per_hour: number;
  // (now - prev) / (prev + 1): smoothed so a 0 -> 5 ticker is finite and
  // outranks one that went 50 -> 60.
  momentum: number;
  change_ratio: number | null;
  // Standard deviations above this run's mean mention count.
  spike_score: number;
  // 0-1 blend of mentions, engagement, unique authors and momentum. Default sort.
  heat_score: number;
  sentiment: 'bullish' | 'bearish' | 'neutral' | string | null;
  sentiment_score: number;
  sentiment_breakdown: Record<string, number>;
  is_emerging: boolean;
  subreddits: Record<string, number>;
  sample_posts: Array<Record<string, unknown>>;
  captured_at?: string | null;
};

export type RedditTrendReport = {
  // False when `reddit-stock-analyzer` is not installed in the deployment;
  // distinct from captured_at === null, which means "not scraped yet".
  available: boolean;
  captured_at: string | null;
  subreddits: string[];
  tickers: RedditTickerTrend[];
  window_hours?: number;
  posts_analyzed?: number;
  posts_in_window?: number;
  mood?: 'bullish' | 'bearish' | 'neutral' | string | null;
  sentiment_score?: number | null;
  rising?: string[];
  fading?: string[];
  emerging?: string[];
};

export type RedditCategories = {
  available: boolean;
  default: string[];
  categories: Record<string, string[]>;
};

export type StockMarketHoursItem = {
  exchange: string;
  session: string;
  is_open: boolean;
  as_of: string | null;
  timezone: string | null;
  next_open: string | null;
  next_close: string | null;
  closure_reason?: 'holiday' | 'weekend' | string | null;
  is_holiday?: boolean;
  holiday_name?: string | null;
};

export type EconomicEventItem = {
  id: string;
  date: string | null;
  time: string | null;
  zone: string | null;
  currency: string | null;
  event: string;
  actual: string | null;
  forecast: string | null;
  previous: string | null;
  impact_score: number | null;
  impact_emoji: string | null;
  source: string | null;
};

export type EarningsSession = 'pre-market' | 'after-hours' | 'unknown';

export type EarningsRow = {
  symbol: string;
  name: string | null;
  date: string;
  session: EarningsSession;
  session_emoji: string | null;
  market_cap: number | null;
  eps_forecast: number | null;
  num_estimates: number | null;
  fiscal_quarter_ending: string | null;
  last_year_eps: number | null;
  last_year_report_date: string | null;
  website: string | null;
};

export type EarningsCalendarDay = {
  date: string;
  count: number;
  rows: EarningsRow[];
};

export type EarningsCalendar = {
  start_date: string;
  end_date: string;
  days: EarningsCalendarDay[];
  source: string;
};

export type ForexMacroCurvePoint = {
  maturity: string;
  symbol: string;
  yield_percent: number;
  change_percent?: number | null;
  website?: string | null;
  source?: string | null;
};

export type ForexMacroCurve = {
  label: string;
  points: ForexMacroCurvePoint[];
  spread_2s10s?: number | null;
};

export type ForexMacroIndex = {
  symbol: string;
  name: string;
  price: number;
  category?: 'crypto' | 'stock' | 'forex' | 'macro' | null;
  change_percent?: number | null;
  website?: string | null;
  source?: string | null;
  tv_symbol?: string | null;
};

export type ForexMacroSnapshot = {
  as_of: string;
  yield_curves: ForexMacroCurve[];
  crypto_indices?: ForexMacroIndex[];
  stock_forex_indices?: ForexMacroIndex[];
  fx_indices: ForexMacroIndex[];
  stock_forex_visible?: boolean;
  market_hours?: Array<Record<string, unknown>>;
  sources?: {
    yield_curves?: string | null;
    crypto_indices?: string | null;
    stock_forex_indices?: string | null;
    fx_indices?: string | null;
    market_hours?: string | null;
  };
};

export type IbkrPosition = {
  id: number;
  account: string;
  symbol: string;
  sec_type: string;
  exchange: string;
  currency: string;
  quantity: number;
  avg_cost: number;
  synced_at: string;
  // enriched by backend
  market_price?: number | null;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  unrealized_pnl_percent: number;
};

export type IbkrTrade = {
  id: number;
  exec_id: string;
  account: string;
  symbol: string;
  sec_type: string;
  currency: string;
  side: 'BOT' | 'SLD' | string;
  quantity: number;
  price: number;
  commission?: number | null;
  executed_at?: string | null;
  created_at: string;
};

export type IbkrAccountValue = {
  value: number;
  currency: string;
};

export type IbkrAccountSummary = {
  NetLiquidation?: IbkrAccountValue;
  TotalCashValue?: IbkrAccountValue;
  UnrealizedPnL?: IbkrAccountValue;
  RealizedPnL?: IbkrAccountValue;
  GrossPositionValue?: IbkrAccountValue;
};

export type IbkrStatus = {
  configured: boolean;
  connected: boolean;
  last_sync: string | null;
  last_error: string | null;
};

export type IntegrationsStatus = {
  signa: boolean;
  reddit: boolean;
};

export type AssetKind = 'all' | 'EQUITY' | 'CRYPTO' | 'FOREX';

export type SentimentLabel = 'BULL' | 'BEAR' | 'NEUTRAL';

export type TrendWindow = '1d' | '7d' | '30d';

/** A value in the active window next to the same value in the window before it. */
export interface TrendPair<T = number> {
  current: T;
  previous: T;
}

/** One of the top tickers in GET /api/overview/trend-summary. */
export interface TrendTicker {
  ticker: string;
  asset_kind: 'EQUITY' | 'CRYPTO' | 'FOREX';
  mentions: number;
  previous_mentions: number;
  /** Rank by mentions in the previous window; null when it wasn't mentioned then. */
  previous_rank: number | null;
  unique_authors: number;
  bull: number;
  bear: number;
  /** (bull - bear) / (bull + bear); null when no mention was directional. */
  net_sentiment: number | null;
  /** Per-bucket series, aligned with TrendSummary.buckets. */
  series: {
    mentions: number[];
    bull: number[];
    bear: number[];
    /** Average price quoted in that bucket's tweets; null when none carried one. */
    price: (number | null)[];
  };
}

/** GET /api/overview/trend-summary — everything the home page trend summary draws. */
export interface TrendSummary {
  window: TrendWindow;
  window_hours: number;
  bucket_hours: number;
  /** Bucket start times (ISO, UTC); the last one is still in progress. */
  buckets: string[];
  /** Oldest stored tweet, so a window reaching further back can be flagged. */
  data_since: string | null;
  totals: {
    tweets: TrendPair;
    authors: TrendPair;
    tickers: TrendPair;
    net_sentiment: TrendPair<number | null>;
    series: {
      tweets: number[];
      authors: number[];
      bull: number[];
      bear: number[];
      tickers: number[];
    };
  };
  kind_share: TrendPair<Record<'EQUITY' | 'CRYPTO' | 'FOREX', number>>;
  tickers: TrendTicker[];
}

export interface MentionHeatCell {
  ticker: string;
  mentions: number;
  avg_sentiment_24h: number; // -1 to 1
  sentiment_label_24h: SentimentLabel;
  asset_kind: string;
  price_direction: number | null;
}

export interface SentimentShiftItem {
  ticker: string;
  mentions_24h: number;
  avg_sentiment_24h: number;
  avg_sentiment_prev: number;
  delta: number;
  sentiment_label_24h: SentimentLabel;
  sentiment_label_prev: SentimentLabel;
  asset_kind: string;
}

export interface VolumeBaselineItem {
  ticker: string;
  mentions_24h: number;
  baseline_7d_avg: number;
  volume_multiplier: number;
  asset_kind: string;
}

export type MentionSignal =
  | 'new'
  | 'resurfacing'
  | 'top'
  | 'hot'
  | 'rising'
  | 'falling'
  | 'neutral';

export type MentionStance = 'bullish' | 'bearish' | 'mixed' | null;

export interface TickerScopeStat {
  mentions: number;
  prev_mentions: number;
  signal: MentionSignal;
  pct_change: number | null;
  rank: number | null;
  days_since_last: number | null;
  first_ever: boolean;
  stance: MentionStance;
  stance_bull: number;
  stance_bear: number;
  stance_total: number;
  stance_flipped: boolean;
  notable: boolean;
}

export interface MentionFrequency {
  personal: TickerScopeStat | null;
  global: TickerScopeStat | null;
}

/** Response shape of POST /api/overview/mention-frequency. */
export interface MentionFrequencyResponse {
  personal: Record<string, Record<string, TickerScopeStat>>;
  global: Record<string, TickerScopeStat>;
}

export interface SectorMentionTicker {
  ticker: string;
  mentions: number;
}

/** Momentum classification for a sector/industry's mentions vs. the prior window (issue #146). */
export type SectorTrend = 'hot' | 'rising' | 'cooling' | 'rare' | 'steady';

export interface SectorMentionIndustry {
  industry: string;
  mentions: number;
  unique_tickers: number;
  top_tickers: SectorMentionTicker[];
  trend?: SectorTrend;
}

export interface SectorMentionItem {
  sector: string;
  mentions: number;
  mention_score: number;
  unique_authors: number;
  unique_tickers: number;
  avg_sentiment_24h: number;
  sentiment_label_24h: SentimentLabel;
  top_tickers: SectorMentionTicker[];
  industries: SectorMentionIndustry[];
  trend?: SectorTrend;
  prev_mentions?: number;
  pct_change?: number | null;
}

export interface HiddenGemItem {
  ticker: string;
  mentions_24h: number;
  gem_subtype: 'new' | 'resurfacing';
  days_since_last: number | null;
  first_seen: string | null;
  last_seen: string | null;
  asset_kind: string;
}

export interface TickerTimeseriesPoint {
  bucket: string;
  mentions: number;
  bullish: number;
  bearish: number;
  neutral: number;
  avg_sentiment: number | null;
}

export interface TickerTimeseriesSummary {
  total_mentions: number;
  avg_mentions_per_bucket: number;
  bullish: number;
  bearish: number;
  neutral: number;
  avg_sentiment: number | null;
  sentiment_label: SentimentLabel;
  unique_authors: number;
  chart_mentions: number;
  avg_engagement: number | null;
  asset_kind: string | null;
  price_direction: number | null;
  first_seen: string | null;
  last_seen: string | null;
}

export interface TickerTimeseries {
  ticker: string;
  window_hours: number;
  bucket_hours: number;
  points: TickerTimeseriesPoint[];
  summary: TickerTimeseriesSummary;
}

export interface TickerPriceHistoryPoint {
  t: string; // ISO timestamp (intraday) or date
  close: number;
  high: number;
  low: number;
}

export interface TickerPriceHistory {
  ticker: string;
  points: TickerPriceHistoryPoint[];
}

export type ExtendedHoursFuture = {
  label: string
  symbol: string
  price: number
  change_pct: number
}

export type ExtendedHoursEtf = {
  symbol: string
  price: number
  extended_price: number | null
  extended_change_pct: number | null
}

export type ExtendedHoursTopTicker = {
  ticker: string
  mentions: number
  sentiment: 'BULL' | 'BEAR' | 'NEUTRAL' | string
}

export type ExtendedHoursTweetStats = {
  total_mentions: number
  top_tickers: ExtendedHoursTopTicker[]
  sentiment_distribution: { BULL: number; BEAR: number; NEUTRAL: number }
}

export type ExtendedHoursSnapshot = {
  session: 'pre-market' | 'after-hours' | 'regular' | 'closed' | string
  window_start: string
  window_end: string
  futures: ExtendedHoursFuture[]
  etfs: ExtendedHoursEtf[]
  tweet_stats: ExtendedHoursTweetStats
}

export type MarketMover = {
  symbol: string
  name: string
  price: number
  extended_price: number
  change_pct: number
  volume: number
  market_cap: number
}

export type MarketMoversSnapshot = {
  session_type: 'pre-market' | 'after-hours' | string
  gainers: MarketMover[]
  losers: MarketMover[]
  stale?: boolean
}

export type Market = 'usa' | 'uk' | 'india' | 'australia' | 'canada' | 'crypto'

export type MoverCategory = 'gainers' | 'losers' | 'most_active' | 'penny_stocks'

export type MoverItem = {
  symbol: string
  name: string
  price: number
  change_pct: number
  volume: number
  market_cap: number
}

export type MoversResponse = {
  market: Market | string
  category: MoverCategory | string
  movers: MoverItem[]
}

export type XStreamState = 'disabled' | 'connecting' | 'ok' | 'auth_failed' | 'error';

export type XStreamStatus = {
  state: XStreamState;
  source: 'cookies' | 'curl' | null;
  detail: string | null;
};
