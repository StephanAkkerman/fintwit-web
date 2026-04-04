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
  assets?: Asset[];
};

export type TreemapCoin = {
  n: string;
  s: string;
  ch: number;
  p: number;
  mc: number;
  mcr: number;
};

export type TreemapResponse = {
  data: TreemapCoin[];
};