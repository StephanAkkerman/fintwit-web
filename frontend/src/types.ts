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

export type AssetFinancials = {
  price?: number | null;
  last_close?: number | null;
  change_percent?: number | null;
  volume?: number | null;
  website?: string | null;
  source?: string | null;
  technical_analysis?: AssetTechnicalAnalysis | null;
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

export type NftTrendingItem = {
  id: string | null;
  name: string;
  symbol: string | null;
  thumb: string | null;
  floor_price: number | null;
  floor_currency: string | null;
  floor_change_24h: number | null;
  website: string | null;
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
