import type { Tweet } from '../types'

export function hasChartSignal(tweet: Tweet): boolean {
  return tweet.has_chart === true
}
