import type { Tweet } from '../types'

export function hasChartSignal(tweet: Tweet): boolean {
  if (tweet.has_chart === true) return true

  if ((tweet.media_types ?? []).some((m) => m === 'photo')) return true

  return (tweet.media ?? []).some((item) => {
    if (typeof item === 'string') {
      return /\.(png|jpe?g|webp|gif)(\?|$)/i.test(item)
    }
    return item?.type === 'photo'
  })
}
