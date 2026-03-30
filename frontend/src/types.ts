export type MediaItem = { url: string; type: string };

export type AnalystRating = {
  date: string;
  price_target: string;
  rating: string;
};

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