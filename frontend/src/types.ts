export type MediaItem = { url: string; type: string };

export type Tweet = {
  id: number;
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
};

export type TickerData = {
  symbol: string;
  name?: string;
  price?: number;
  change?: number;
  change_percent?: number;
};

export type MarketMoversResponse = {
  trending: TickerData[];
  gainers: TickerData[];
  losers: TickerData[];
};