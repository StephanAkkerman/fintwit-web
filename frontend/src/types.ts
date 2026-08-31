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
};

/**
 * Slow-moving valuation/volume metrics from the classifier's Yahoo quote.
 * Every field is optional: only what Yahoo actually reported is present, so a
 * missing field means "unknown", never zero.
 */
export type AssetFundamentals = {
  market_cap?: number | null;
  forward_pe?: number | null;
  trailing_pe?: number | null;
  eps_forward?: number | null;
  eps_trailing?: number | null;
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
  has_chart?: boolean | null;
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

export type AssetKind = 'all' | 'EQUITY' | 'CRYPTO' | 'FOREX';

export type SentimentLabel = 'BULL' | 'BEAR' | 'NEUTRAL';

export interface MacroTickerItem {
  label: string; // "SPX" | "NDX" | "BTC" | "ETH" | "DXY" | "VIX" | "GOLD"
  symbol: string;
  price: number;
  change_pct: number;
  sparkline: number[]; // [] until intraday bars are added
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

export interface HiddenGemItem {
  ticker: string;
  mentions_24h: number;
  gem_subtype: 'new' | 'resurfacing';
  days_since_last: number | null;
  first_seen: string | null;
  last_seen: string | null;
  asset_kind: string;
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
