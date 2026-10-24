export type AccessAllowlist = { emails: string[] };

export type MediaItem = { url: string; type: string };

export type AssetTradingViewSummary = {
  interval?: "four_h" | "one_d" | string | null;
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

/** One symbol's daily indicators from `/api/research/indicators`. */
export type TechnicalIndicators = {
  symbol: string;
  /** `tradingview` (scanner) or `price_history` (computed fallback, no ratings). */
  source: "tradingview" | "price_history" | string;
  tv_symbol?: string | null;
  type?: string | null;
  price: number;
  rsi: {
    value: number | null;
    state: "overbought" | "oversold" | "neutral" | null;
    four_h?: number | null;
  };
  macd: {
    macd: number | null;
    signal: number | null;
    histogram: number | null;
    above_signal: boolean | null;
    cross: "bullish" | "bearish" | null;
  };
  moving_averages: {
    sma20: number | null;
    sma50: number | null;
    sma200: number | null;
    price_vs_sma20_percent: number | null;
    price_vs_sma50_percent: number | null;
    price_vs_sma200_percent: number | null;
    sma50_vs_sma200: "golden_cross" | "death_cross" | null;
    cross_today: "golden_cross" | "death_cross" | null;
  };
  atr: { value: number | null; percent_of_price: number | null };
  adx: {
    value: number | null;
    trend_strength: "strong" | "moderate" | "weak" | null;
    direction: "up" | "down" | null;
  };
  volume: { today: number | null; avg_30d: number | null; vs_avg_30d: number | null };
  rating: {
    one_d: string | null;
    four_h: string | null;
    moving_averages: string | null;
    oscillators: string | null;
  };
  signals: string[];
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
  session?: "regular" | "pre-market" | "after-hours" | "closed" | string | null;
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
  right: "CALL" | "PUT" | string;
  strike?: number | null;
  expiry?: string | null;
  notional_usd?: number | null;
  // Per-contract price or average fill; only the NER model reports it.
  price?: number | null;
  source?: string | null;
};

/** GET /api/options/contract: the current quote for a contract a tweet names. */
export type OptionContractQuote = {
  symbol: string;
  right: "CALL" | "PUT" | string;
  strike: number;
  status: "listed" | "expired" | string;
  expiration: string;
  last_price?: number | null;
  bid?: number | null;
  ask?: number | null;
  mid?: number | null;
  change_percent?: number | null;
  implied_volatility?: number | null;
  volume?: number | null;
  open_interest?: number | null;
  in_the_money?: boolean | null;
  underlying_price?: number | null;
};

export type TweetOptionsContext = {
  classification: "OPTIONS" | "SPOT_OR_OTHER" | string;
  score: number;
  confidence: "low" | "medium" | "high" | string;
  side: "CALL" | "PUT" | "MIXED" | "UNKNOWN" | string;
  contract_count: number;
  contracts: TweetOptionContract[];
  keyword_hits: string[];
  cashtags: string[];
  // Present when the NER model (issue #64) classified the tweet: the raw
  // entity texts per label, and whether only the quoted tweet was options.
  entities?: Record<string, string[]>;
  from_quote?: boolean;
  source?: "model" | string;
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
  session?: "regular" | "pre" | "post" | string | null;
};

export type Tweet = {
  id: number;
  text: string;
  user_name: string;
  user_screen_name: string;
  user_img: string;
  url: string;
  created_at: string;
  // When the poster last edited the post on X; null when never edited.
  edited_at?: string | null;
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
  sentiment_label?: "BULLISH" | "BEARISH" | "NEUTRAL" | string | null;
  sentiment_emoji?: string | null;
  sentiment_score?: number | null;
  quoted_user_name?: string | null;
  quoted_user_screen_name?: string | null;
  quoted_user_img?: string | null;
  quoted_url?: string | null;
  quoted_created_at?: string | null;
  quoted_tweet?: QuotedTweet | null;
  quoted_sentiment_label?: "BULLISH" | "BEARISH" | "NEUTRAL" | string | null;
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
  direction?: "BULLISH" | "BEARISH" | string | null;
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
  direction?: "BULLISH" | "BEARISH" | string | null;
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
  return_pct: number; // raw price move, not signed for direction
  correct: boolean;
  // Left out of every score: the re-priced quote evidently belongs to a
  // different asset than the one priced at call time.
  excluded: boolean;
  evaluated_at: string;
};

export type TraderCall = {
  id: number;
  tweet_id: number;
  ticker: string;
  direction: "bullish" | "bearish";
  sentiment_score: number | null;
  asset_kind: string | null;
  price_at_call: number;
  called_at: string;
  tweet_text: string | null; // null once the source tweet is no longer stored
  tweet_url: string | null;
  results: TraderCallResult[]; // empty while every horizon is still pending
};

export type TraderHorizonStat = {
  horizon_days: TraderCallHorizon;
  graded_calls: number;
  correct_calls: number;
  hit_rate: number | null;
  avg_return_pct: number | null;
};

export type TraderSummary = {
  total_calls: number;
  bullish_calls: number;
  bearish_calls: number;
  distinct_tickers: number;
  first_called_at: string | null;
  last_called_at: string | null;
};

// One ticker a trader has called, graded at the detail's `horizon_days`.
export type TraderTickerStat = {
  ticker: string;
  asset_kind: string | null;
  calls: number;
  bullish_calls: number;
  bearish_calls: number;
  last_called_at: string | null;
  graded_calls: number;
  correct_calls: number;
  hit_rate: number | null;
  avg_return_pct: number | null;
};

export type TraderDetail = {
  user_screen_name: string;
  horizon_days: TraderCallHorizon;
  summary: TraderSummary;
  horizons: TraderHorizonStat[];
  tickers: TraderTickerStat[];
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

export type StocktwitsKeyword = "ts" | "m_day" | "wl_ct_day";

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
  "Issue Symbol": string;
  "Resumption Time"?: string;
};

export type StockFearGreedData = {
  value: number;
  status: string;
  change?: string | null;
};

export type StockFearGreedWindow = 7 | 30;

export type StockFearGreedHistory = {
  days: StockFearGreedWindow;
  points: Array<{ date: string; value: number }>;
  source: "cnn" | "feargreedmeter" | string;
};

export type OptionContractActivity = {
  symbol: string;
  contract_type: "CALL" | "PUT" | string;
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
  option_type: "CALL" | "PUT" | string;
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

export type GammaRegime = "positive" | "negative";

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

export type FuturesCrowding = "crowded_short" | "neutral" | "crowded_long";

export type FuturesPositioning = {
  code: string;
  name: string;
  report_date: string;
  open_interest: number;
  lev_net: number;
  lev_net_pct_oi: number;
  lev_net_change: number | null;
  lev_percentile: number;
  asset_mgr_net: number;
  asset_mgr_net_pct_oi: number;
  crowding: FuturesCrowding;
  weeks_ranked: number;
  history: Array<{ date: string; lev_net_pct_oi: number }>;
};

export type CtaExposure = "max_long" | "long" | "flat" | "short" | "max_short";

export type CtaSignal = {
  lookback: string;
  days: number;
  trigger: number;
  distance_pct: number;
  signal: "long" | "short";
};

export type CtaTriggers = {
  symbol: string;
  spot: number;
  score: number;
  exposure: CtaExposure;
  signals: CtaSignal[];
  nearest_trigger: string;
};

export type ConcentrationWindow = {
  window: string;
  cap_weighted_pct: number;
  equal_weighted_pct: number;
  spread_pp: number;
};

export type MarketConcentration = {
  cap_weighted: string;
  equal_weighted: string;
  trend: "narrowing" | "stable" | "broadening";
  headline_window: string;
  windows: ConcentrationWindow[];
  ratio_history: Array<{ date: string; ratio: number }>;
};

export type MarketPositioning = {
  futures: FuturesPositioning[] | null;
  cta: CtaTriggers | null;
  concentration: MarketConcentration | null;
  as_of: string;
};

export type PutCallKey = "total" | "equity" | "index" | "etp" | "spx" | "vix";

export type PutCallSentiment = "fear" | "neutral" | "greed";

export type PutCallRatio = {
  key: PutCallKey;
  value: number;
  previous: number | null;
  change: number | null;
  average: number | null;
};

export type PutCallVolume = {
  call: number | null;
  put: number | null;
};

export type PutCallHistoryPoint = {
  date: string;
  total: number | null;
  equity: number | null;
  index: number | null;
};

export type PutCallRatios = {
  date: string;
  ratios: PutCallRatio[];
  volume: Partial<Record<"total" | "equity" | "index", PutCallVolume>>;
  sentiment: PutCallSentiment | null;
  thresholds: { fear: number; greed: number };
  history: PutCallHistoryPoint[];
  source: string;
};

export type WorldIndexRegionKey = "asia" | "europe" | "us_futures";

export type WorldIndex = {
  symbol: string;
  name: string;
  /** ISO 3166 alpha-2, or "EU" for the Euro Stoxx 50. */
  country: string;
  region: WorldIndexRegionKey;
  price: number;
  change_percent: number | null;
  timezone: string;
  /** Which US names or sectors this market tends to move. */
  read_through: string;
  tags: string[];
  tv_symbol: string;
  website?: string | null;
  /** null for futures when TradingView reports no session. */
  is_open: boolean | null;
  /** Local date of the session the change belongs to; null for futures. */
  session_date: string | null;
  next_open: string | null;
};

export type WorldIndexRegion = {
  key: WorldIndexRegionKey;
  label: string;
  avg_change_percent: number | null;
  indices: WorldIndex[];
};

export type WorldIndices = {
  as_of: string;
  regions: WorldIndexRegion[];
  /** Average move of the chip-heavy indices (Nikkei, KOSPI, TAIEX, AEX). */
  semis: {
    avg_change_percent: number;
    tone: "bearish" | "neutral" | "bullish";
    symbols: string[];
  } | null;
  source: string;
};

export type CompanyNewsArticle = {
  symbols: string[];
  title: string;
  excerpt?: string | null;
  url: string;
  date: string;
  source?: string | null;
  /** FinTwitBERT read of headline + excerpt; null when the model is not loaded. */
  sentiment_label?: "BULLISH" | "BEARISH" | "NEUTRAL" | null;
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
  label: "BULLISH" | "BEARISH" | "NEUTRAL" | null;
};

export type CompanyNewsResponse = {
  articles: CompanyNewsArticle[];
  sentiment: CompanyNewsSentimentSummary;
  source: string;
};

export type NewsStoryLink = {
  title: string;
  url: string;
  source?: string | null;
};

/** One event in the news overview: its headlines grouped and ranked (issue #217). */
export type NewsStory = {
  title: string;
  url: string;
  source?: string | null;
  date: string;
  /** Leading sentences of the summary Yahoo scraped for the lead article. */
  summary: string;
  symbols: string[];
  /** Every outlet that ran a headline about this event. */
  sources: string[];
  article_count: number;
  themes: string[];
  sentiment_label?: "BULLISH" | "BEARISH" | "NEUTRAL" | null;
  sentiment_score?: number | null;
  /** The other headlines about the same event. */
  related: NewsStoryLink[];
  score: number;
};

export type NewsTheme = {
  name: string;
  count: number;
};

export type NewsOverviewResponse = {
  symbols: string[];
  top_stories: NewsStory[];
  themes: NewsTheme[];
  articles: CompanyNewsArticle[];
  sentiment: CompanyNewsSentimentSummary;
  generated_at: string;
  source: string;
};

export type SpyHeatmapDateRange =
  | "one_day"
  | "after_hours"
  | "yesterday"
  | "one_week"
  | "one_month"
  | "ytd"
  | "one_year";

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

export type SectorRotationTimeframe = "daily" | "weekly";

export type SectorRotationQuadrant =
  | "leading"
  | "weakening"
  | "lagging"
  | "improving";

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
  broker: "IBKR";
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

/** ibkr = IBKR's live mark, yahoo = Yahoo quote, ibkr_stale = last IBKR mark, none = no price */
export type PortfolioPriceSource = "ibkr" | "yahoo" | "ibkr_stale" | "none";

export type PortfolioSummaryPosition = PortfolioPosition & {
  quote_symbol?: string;
  price_source?: PortfolioPriceSource;
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

export type PortfolioHoldingSource = "auto" | "manual" | "ibkr";

export type PortfolioHistoryRange =
  | "1W"
  | "1M"
  | "3M"
  | "6M"
  | "YTD"
  | "1Y"
  | "5Y"
  | "MAX";

export type PortfolioHistoryPoint = {
  t: string;
  value: number;
  cost_basis: number;
  pnl: number;
  pnl_percent: number;
  /** Where the point came from: a stored snapshot, price reconstruction, or the live quote. */
  source: "snapshot" | "reconstructed" | "live";
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

export type PortfolioFlagTone = "bullish" | "bearish" | "neutral";

export type PortfolioAssetFlag = {
  code:
    | "at_ath"
    | "near_ath"
    | "recent_ath"
    | "at_atl"
    | "near_atl"
    | "recent_atl"
    | "near_52w_high"
    | "near_52w_low";
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
  /** Symbol quotes/history come from, e.g. ARKG.L for an LSE listing */
  quote_symbol?: string;
  market_price: number | null;
  price_source?: PortfolioPriceSource;
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
  | "unrated"
  | "concentrated"
  | "moderate"
  | "diversified";

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
  // How the post carries media; null for a text post. Older backends omit it.
  media_type?: "image" | "gallery" | "video" | "link" | null;
  // External page a link post points at; `url` is always the Reddit thread.
  link_url?: string | null;
  flair?: string | null;
  upvote_ratio?: number | null;
  over_18?: boolean;
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
  sentiment: "bullish" | "bearish" | "neutral" | string | null;
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
  mood?: "bullish" | "bearish" | "neutral" | string | null;
  sentiment_score?: number | null;
  rising?: string[];
  fading?: string[];
  emerging?: string[];
  sentiment_breakdown?: Record<string, number>;
  by_subreddit?: RedditSubredditSummary[];
  timeline?: RedditTrendTimeline;
  worker?: RedditTrendWorkerStatus;
};

// One subreddit's slice of a trend run (SubredditSummary in the package).
export type RedditSubredditSummary = {
  subreddit: string;
  posts: number;
  posts_with_tickers?: number;
  mood?: "bullish" | "bearish" | "neutral" | string | null;
  sentiment_score?: number;
  sentiment_breakdown?: Record<string, number>;
  top_tickers?: Record<string, number>;
};

// Hourly mention counts for the run's top tickers, oldest bucket first.
export type RedditTrendTimeline = {
  bucket_seconds?: number;
  bucket_starts?: number[];
  series?: Record<string, number[]>;
};

// What the background scrape is doing (app/runtime/reddit_trends.py).
export type RedditTrendWorkerStatus = {
  state:
    | "idle"
    | "disabled"
    | "warming_up"
    | "scraping"
    | "ok"
    | "empty"
    | "error"
    | "unavailable"
    | string;
  last_attempt_at?: string | null;
  last_success_at?: string | null;
  last_error?: string | null;
  last_posts_analyzed?: number | null;
  next_attempt_at?: string | null;
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
  closure_reason?: "holiday" | "weekend" | string | null;
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

export type CongressTransaction = "buy" | "sell" | "exchange" | "other";

export type CongressTrade = {
  id: string | null;
  ticker: string | null;
  asset: string | null;
  asset_type: string | null;
  transaction: CongressTransaction;
  transaction_label: string;
  amount_range: string | null;
  amount_min: number | null;
  amount_max: number | null;
  politician: string;
  chamber: string | null;
  party: string | null;
  party_name: string | null;
  filed: string | null;
  traded: string | null;
  description: string | null;
  /** Quiver's estimate of the stock's move since the trade, minus the market's. */
  excess_return_pct: number | null;
  photo_url: string | null;
  bioguide_id: string | null;
  website: string | null;
};

export type CongressTickerFlow = {
  ticker: string;
  trades: number;
  politicians: string[];
};

export type CongressPolitician = {
  name: string;
  party: string | null;
  chamber: string | null;
  trades: number;
  buys: number;
  sells: number;
  last_filed: string | null;
};

export type CongressTrades = {
  trades: CongressTrade[];
  summary: {
    trades: number;
    buys: number;
    sells: number;
    most_bought: CongressTickerFlow[];
    most_sold: CongressTickerFlow[];
    politicians: CongressPolitician[];
  };
  filter: { politician: string | null; stocks_only: boolean };
  as_of: string | null;
  source: string;
};

export type EarningsSession = "pre-market" | "after-hours" | "unknown";

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
  /** Reported EPS, once the company has reported (fintwit-bot #296). */
  eps_actual?: number | null;
  /** Nasdaq's surprise vs consensus, in percent. */
  surprise_pct?: number | null;
};

export type EarningsOutcome = "beat" | "miss" | "inline";

export type EarningsResult = EarningsRow & {
  eps_actual: number;
  surprise_pct: number | null;
  outcome: EarningsOutcome | null;
};

export type EarningsResults = {
  start_date: string;
  end_date: string;
  results: EarningsResult[];
  summary: { reported: number; beat: number; miss: number; inline: number };
  source: string;
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
  category?: "crypto" | "stock" | "forex" | "macro" | null;
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
  primary_exchange?: string | null;
  con_id?: number | null;
  local_symbol?: string | null;
  // IBKR's own mark at sync time
  ibkr_market_price?: number | null;
  ibkr_market_value?: number | null;
  ibkr_unrealized_pnl?: number | null;
  // contract terms (options/futures); null for stocks
  expiry?: string | null;
  strike?: number | null;
  right?: string | null;
  multiplier?: number | null;
  // enriched by backend
  description?: string;
  quote_symbol?: string | null;
  market_price?: number | null;
  price_source?: PortfolioPriceSource;
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
  side: "BOT" | "SLD" | string;
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

export type IbkrSessionState =
  | 'ok'
  | 'stale'
  | 'logged_out'
  | 'disconnected'
  | 'restarting'
  | 'off';

export type IbkrStatus = {
  configured: boolean;
  /** Only true while the gateway is syncing (`state === 'ok'`). */
  connected: boolean;
  /** Absent from backends that predate session tracking. */
  state?: IbkrSessionState;
  /** Whether the backend can restart the gateway for a fresh 2FA login. */
  relogin_available?: boolean;
  last_sync: string | null;
  last_error: string | null;
};

export type FxRates = {
  base: string;
  rates: Record<string, number>;
};

export type IntegrationsStatus = {
  signa: boolean;
  reddit: boolean;
};

export type AssetKind = "all" | "EQUITY" | "CRYPTO" | "FOREX";

export type SentimentLabel = "BULL" | "BEAR" | "NEUTRAL";

export type TrendWindow = "1d" | "7d" | "30d";

/** A value in the active window next to the same value in the window before it. */
export interface TrendPair<T = number> {
  current: T;
  previous: T;
}

/** One of the top tickers in GET /api/overview/trend-summary. */
export interface TrendTicker {
  ticker: string;
  asset_kind: "EQUITY" | "CRYPTO" | "FOREX";
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
  kind_share: TrendPair<Record<"EQUITY" | "CRYPTO" | "FOREX", number>>;
  tickers: TrendTicker[];
}

export interface MentionHeatCell {
  ticker: string;
  mentions: number;
  /** Fairness-adjusted score (per-author cap); used for ranking and sizing. */
  mention_score?: number;
  unique_authors?: number;
  avg_sentiment_24h: number; // -1 to 1
  sentiment_label_24h: SentimentLabel;
  asset_kind: string;
  /** Equity sector/industry from ticker-classifier; null for crypto, forex and most ETFs. */
  sector?: string | null;
  industry?: string | null;
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
  | "new"
  | "resurfacing"
  | "top"
  | "hot"
  | "rising"
  | "falling"
  | "neutral";

export type MentionStance = "bullish" | "bearish" | "mixed" | null;

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
export type SectorTrend = "hot" | "rising" | "cooling" | "rare" | "steady";

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
  gem_subtype: "new" | "resurfacing";
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
  label: string;
  symbol: string;
  price: number;
  change_pct: number;
};

export type ExtendedHoursEtf = {
  symbol: string;
  price: number;
  extended_price: number | null;
  extended_change_pct: number | null;
};

export type ExtendedHoursTopTicker = {
  ticker: string;
  mentions: number;
  sentiment: "BULL" | "BEAR" | "NEUTRAL" | string;
};

export type ExtendedHoursTweetStats = {
  total_mentions: number;
  top_tickers: ExtendedHoursTopTicker[];
  sentiment_distribution: { BULL: number; BEAR: number; NEUTRAL: number };
};

export type ExtendedHoursSnapshot = {
  session: "pre-market" | "after-hours" | "regular" | "closed" | string;
  window_start: string;
  window_end: string;
  futures: ExtendedHoursFuture[];
  etfs: ExtendedHoursEtf[];
  tweet_stats: ExtendedHoursTweetStats;
};

export type MarketMover = {
  symbol: string;
  name: string;
  price: number;
  extended_price: number;
  change_pct: number;
  volume: number;
  market_cap: number;
};

export type MarketMoversSnapshot = {
  session_type: "pre-market" | "after-hours" | string;
  gainers: MarketMover[];
  losers: MarketMover[];
  stale?: boolean;
};

export type Market = "usa" | "uk" | "india" | "australia" | "canada" | "crypto";

export type MoverCategory =
  | "gainers"
  | "losers"
  | "most_active"
  | "penny_stocks";

export type MoverItem = {
  symbol: string;
  name: string;
  price: number;
  change_pct: number;
  volume: number;
  market_cap: number;
};

export type MoversResponse = {
  market: Market | string;
  category: MoverCategory | string;
  movers: MoverItem[];
};

export type XStreamState =
  | "disabled"
  | "connecting"
  | "ok"
  | "auth_failed"
  | "error"
  | "stalled";

export type XStreamStatus = {
  state: XStreamState;
  source: "cookies" | "curl" | null;
  detail: string | null;
};

// Claude market check (/advisor): the owner's strategy and Claude's journal.
export type AdvisorAction = "buy" | "add" | "trim" | "sell" | "watch";

export interface AdvisorStrategy {
  rules: string;
  watchlist: string[];
  /** X handles whose ticker mentions Claude vets as buy ideas. */
  followed_traders: string[];
  /** Cash the owner is willing to invest; null when not set. */
  available_cash: number | null;
  cash_currency: string | null;
  updated_at: string | null;
}

export type AdvisorStrategyDraft = Pick<
  AdvisorStrategy,
  "rules" | "watchlist" | "followed_traders" | "available_cash"
> & {
  cash_currency: string;
};

/** One finished market check: when it ran and what it found. */
export interface AdvisorRun {
  id: number;
  ran_at: string | null;
  /** Newest tweet id the check read (a string: ids overflow a JS number). */
  tweet_cursor: string | null;
  session: string | null;
  posts_read: number | null;
  summary: string;
}

export interface AdvisorCallResult {
  horizon_days: number;
  price_at_horizon: number;
  return_pct: number;
  correct: boolean;
  excluded: boolean;
  evaluated_at: string | null;
}

export interface AdvisorCall {
  id: number;
  symbol: string;
  action: AdvisorAction;
  conviction: "low" | "medium" | "high" | null;
  price_at_call: number | null;
  asset_kind: string | null;
  reasoning: string;
  rule: string | null;
  /** A paper strategy's key, or null for advice to the owner. */
  strategy?: string | null;
  called_at: string | null;
  results: Record<string, AdvisorCallResult>;
}

export interface AdvisorScoreBucket {
  graded: number;
  hit_rate: number | null;
  avg_return_pct: number | null;
}

export interface AdvisorScorecard {
  total_calls: number;
  horizons: Record<
    string,
    AdvisorScoreBucket & { by_action: Record<string, AdvisorScoreBucket> }
  >;
  /** Each paper strategy's entries, scored apart: strategy -> horizon -> bucket. */
  strategies?: Record<string, Record<string, AdvisorScoreBucket>>;
}

export interface PaperPosition {
  symbol: string;
  entry_call_id: number;
  entry_price: number;
  entered_at: string | null;
  exit_price: number | null;
  exited_at: string | null;
  /** "sell", or "held N days" when the holding period ran out. */
  exit_reason: string | null;
  status: "open" | "closed";
  price_now: number | null;
  return_pct: number | null;
  days_held: number | null;
}

/** One rule-based strategy the market check paper-trades (GET /api/advisor/paper). */
export interface PaperPortfolio {
  strategy: string;
  label: string;
  entry: string;
  exit: string;
  max_hold_days: number | null;
  positions: PaperPosition[];
  open: number;
  closed: number;
  /** Share of closed positions that made money. */
  win_rate: number | null;
  /** Equal money in every position, open ones marked at today's price. */
  avg_return_pct: number | null;
  scores: Record<string, AdvisorScoreBucket>;
}

export type InsiderTrade = {
  filed_at: string | null;
  traded: string | null;
  ticker: string;
  company: string | null;
  insider: string | null;
  insider_cik: string | null;
  title: string | null;
  is_officer: boolean;
  is_ten_percent_owner: boolean;
  side: "buy" | "sell";
  trade_label: string;
  with_option_exercise: boolean;
  price: number | null;
  shares: number | null;
  owned_after: number | null;
  owned_change_pct: number | null;
  new_position: boolean;
  value: number | null;
  remarks: string[];
  filing_url: string | null;
};

export type InsiderTickerGroup = {
  ticker: string;
  company: string | null;
  insiders: string[];
  officers: string[];
  trades: number;
  value: number;
  last_traded: string | null;
  last_price: number | null;
};

export type InsiderTrades = {
  trades: InsiderTrade[];
  summary: {
    buys: number;
    sells: number;
    buy_value: number;
    sell_value: number;
    buy_share_pct: number | null;
    cluster_buys: InsiderTickerGroup[];
    top_buys: InsiderTickerGroup[];
    top_sells: InsiderTickerGroup[];
  };
  filter: {
    days: number;
    min_value: number;
    ticker: string | null;
    side: "buy" | "sell" | null;
  };
  as_of: string | null;
  source: string;
};

export type FundAction = "new" | "added" | "reduced" | "sold_out" | "unchanged";

export type FundPosition = {
  cusip: string;
  issuer: string | null;
  ticker: string | null;
  instrument: "call" | "put" | "note" | null;
  value: number;
  shares: number;
  prev_shares: number;
  weight_pct: number;
  action: FundAction;
  shares_change_pct: number | null;
  value_change: number;
};

export type Fund = {
  cik: number;
  name: string;
  manager: string | null;
  report_date: string;
  filed: string;
  prev_report_date: string | null;
  filing_url: string;
  positions: number;
  total_value: number;
  top_holdings: FundPosition[];
  buys: FundPosition[];
  sells: FundPosition[];
  new_positions: number;
  sold_out: number;
  stale: boolean;
};

export type FundConsensus = {
  cusip: string;
  issuer: string | null;
  ticker: string | null;
  funds: string[];
  new_or_exited?: number;
  value_change?: number;
  value?: number;
};

export type FundHoldings = {
  funds: Fund[];
  most_bought: FundConsensus[];
  most_sold: FundConsensus[];
  most_held: FundConsensus[];
  report_date: string | null;
  missing: string[];
  as_of: string | null;
  source: string;
};

export type BreadthTrend =
  | "overbought"
  | "healthy"
  | "mixed"
  | "weak"
  | "washed_out";

export type BreadthDay =
  | "broad_rally"
  | "narrow_rally"
  | "broad_selloff"
  | "resilient"
  | "mixed";

export type BreadthCounts = {
  members: number;
  advancers: number;
  decliners: number;
  new_highs: number;
  new_lows: number;
  pct_above_sma50: number | null;
  pct_above_sma200: number | null;
};

export type BreadthUniverse = BreadthCounts & {
  key: string;
  label: string;
  benchmark: {
    symbol: string;
    price: number | null;
    change_pct: number | null;
  };
  unchanged: number;
  advancers_pct: number | null;
  pct_above_sma20: number | null;
  read: {
    trend: { key: BreadthTrend; label: string } | null;
    day: BreadthDay;
    note: string;
  };
};

export type BreadthSector = BreadthCounts & {
  sector: string;
  avg_change: number | null;
};

export type MarketBreadth = {
  universes: BreadthUniverse[];
  sectors: BreadthSector[];
  session_date: string | null;
  as_of: string;
  source: string;
};

export type MarketBreadthPoint = {
  universe: string;
  session_date: string;
  captured_at: string | null;
  members: number;
  advancers: number;
  decliners: number;
  new_highs: number;
  new_lows: number;
  pct_above_sma20: number | null;
  pct_above_sma50: number | null;
  pct_above_sma200: number | null;
  benchmark_change_pct: number | null;
};
