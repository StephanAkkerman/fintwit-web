export type MediaItem = { url: string; type: string };

export type TreemapCoin = {
  s: string; // symbol
  n: string; // name
  p: number; // price
  ch: number; // 24h change
  mc: number; // market cap
  v: number; // volume
};

export type TreemapResponse = {
  data: TreemapCoin[];
  categories: string[];
  timestamp: number;
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
};