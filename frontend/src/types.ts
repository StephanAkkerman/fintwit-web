export type MediaItem = { url: string; type: string };

export type AssetFinancials = {
  price?: number | null;
  change_percent?: number | null;
  volume?: number | null;
  website?: string | null;
};

export type Asset = {
  symbol: string;
  kind?: string | null;
  name?: string | null;
  market_cap?: number | null;
  meta?: unknown;
  financials?: AssetFinancials | null;
};

export type Tweet = {
  id: number;
  text: string;
  user_name: string;
  user_screen_name: string;
  user_img: string;
  url: string;
  created_at: string;
  media: MediaItem[];
  tickers: string[];
  hashtags: string[];
  title: string;
  media_types: string[];
  replies: number;
  likes: number;
  views: number;
  retweets: number;
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
