import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import TweetCard from '../components/TweetCard'
import type { Tweet } from '../types'

const baseTweet: Tweet = {
  id: 1,
  text: 'Hello world',
  user_name: 'Test User',
  user_screen_name: 'testuser',
  user_img: 'https://example.com/avatar.jpg',
  url: 'https://x.com/testuser/status/1',
  media: [],
  tickers: [],
  hashtags: [],
  title: '',
  media_types: [],
}

describe('TweetCard', () => {
  it('renders user name and screen name', () => {
    render(<TweetCard t={baseTweet} />)
    expect(screen.getByText('Test User')).toBeInTheDocument()
    expect(screen.getByText('@testuser')).toBeInTheDocument()
  })

  it('renders tweet text', () => {
    render(<TweetCard t={baseTweet} />)
    expect(screen.getByText('Hello world')).toBeInTheDocument()
  })

  it('renders an Open link pointing to the tweet URL', () => {
    render(<TweetCard t={baseTweet} />)
    const link = screen.getByRole('link', { name: /open/i })
    expect(link).toHaveAttribute('href', baseTweet.url)
  })

  it('renders tickers as pill badges', () => {
    render(<TweetCard t={{ ...baseTweet, tickers: ['AAPL', 'TSLA'] }} />)
    expect(screen.getByText('$AAPL')).toBeInTheDocument()
    expect(screen.getByText('$TSLA')).toBeInTheDocument()
  })

  it('renders hashtags as pill badges', () => {
    render(<TweetCard t={{ ...baseTweet, hashtags: ['crypto', 'stocks'] }} />)
    expect(screen.getByText('#crypto')).toBeInTheDocument()
    expect(screen.getByText('#stocks')).toBeInTheDocument()
  })

  it('renders media images when present', () => {
    const tweetWithMedia: Tweet = {
      ...baseTweet,
      media: [
        { url: 'https://example.com/img1.jpg', type: 'photo' },
        { url: 'https://example.com/img2.jpg', type: 'photo' },
      ],
    }
    render(<TweetCard t={tweetWithMedia} />)
    const images = screen.getAllByRole('img')
    // First image is the avatar, the next two are media
    const mediaImgs = images.filter((img) =>
      (img as HTMLImageElement).src.includes('img')
    )
    expect(mediaImgs).toHaveLength(2)
  })

  it('does not render media section when media array is empty', () => {
    const { container } = render(<TweetCard t={baseTweet} />)
    // Only avatar image should be present
    const images = container.querySelectorAll('img')
    expect(images).toHaveLength(1)
  })
})
