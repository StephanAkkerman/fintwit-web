import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
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

  it('renders quote-tweet markdown as blockquote with parsed links', () => {
    const quoteText =
      '> [@opensea](https://twitter.com/opensea):\n> Treasure Chests from our final Wave are now unlocked.'

    const { container } = render(<TweetCard t={{ ...baseTweet, text: quoteText }} />)

    expect(container.querySelector('blockquote')).toBeInTheDocument()
    expect(screen.getByText('Quoted post')).toBeInTheDocument()
    const quoteUserLink = screen.getByRole('link', { name: '@opensea' })
    expect(quoteUserLink).toHaveAttribute('href', 'https://twitter.com/opensea')
  })

  it('renders quoted image inside the quote embed', () => {
    const quoteText =
      '> [@opensea](https://twitter.com/opensea):\n> Treasure Chests from our final Wave are now unlocked.'

    render(
      <TweetCard
        t={{
          ...baseTweet,
          text: quoteText,
          media: [
            { url: 'https://example.com/inline.jpg', type: 'photo' },
            { url: 'https://example.com/quoted.jpg', type: 'photo' },
          ],
        }}
      />
    )

    const quotedImage = screen.getByAltText('Quoted media') as HTMLImageElement
    expect(quotedImage.src).toContain('quoted.jpg')

    const inlineImage = screen.getByAltText('photo') as HTMLImageElement
    expect(inlineImage.src).toContain('inline.jpg')

    const quoteBlock = screen.getByText('Quoted post').closest('blockquote')
    expect(quoteBlock).toBeInTheDocument()
    expect(quoteBlock?.compareDocumentPosition(inlineImage) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy()
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
    expect(screen.getByText('#CRYPTO')).toBeInTheDocument()
    expect(screen.getByText('#STOCKS')).toBeInTheDocument()
  })

  it('falls back to text parsing for ticker and hashtag badges', () => {
    render(<TweetCard t={{ ...baseTweet, text: 'Watching $aapl and #btc now' }} />)
    expect(screen.getByText('$AAPL')).toBeInTheDocument()
    expect(screen.getByText('#BTC')).toBeInTheDocument()
  })

  it('shows chart badge when has_chart flag is true', () => {
    render(<TweetCard t={{ ...baseTweet, has_chart: true }} />)
    expect(screen.getByLabelText('Chart tweet')).toBeInTheDocument()
  })

  it('shows chart badge when tweet has photo media', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          media: [{ url: 'https://example.com/chart.jpg', type: 'photo' }],
          media_types: ['photo'],
        }}
      />
    )

    expect(screen.getByLabelText('Chart tweet')).toBeInTheDocument()
  })

  it('renders sentiment badge when sentiment fields are available', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          sentiment_label: 'BULLISH',
          sentiment_emoji: '🐂',
          sentiment_score: 0.97,
        }}
      />
    )

    expect(screen.getByLabelText('Tweet sentiment')).toBeInTheDocument()
    expect(screen.getByText(/bullish/i)).toBeInTheDocument()
  })

  it('does not show chart badge for text-only tweets', () => {
    render(<TweetCard t={baseTweet} />)
    expect(screen.queryByLabelText('Chart tweet')).not.toBeInTheDocument()
  })

  it('renders asset financial information when available', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          assets: [
            {
              symbol: 'AAPL',
              kind: 'EQUITY',
              name: 'Apple Inc.',
              financials: {
                price: 185.12,
                change_percent: 1.73,
              },
            },
          ],
        }}
      />
    )

    expect(screen.getByText('$AAPL')).toBeInTheDocument()
    expect(screen.getByText(/^\$185[.,]12$/)).toBeInTheDocument()
    expect(screen.getByText('+1.73%')).toBeInTheDocument()
  })

  it('calls ticker filter callback when financial ticker is clicked', () => {
    const onTickerSelect = vi.fn()

    render(
      <TweetCard
        t={{
          ...baseTweet,
          assets: [{ symbol: 'SOL', kind: 'crypto', financials: { price: 150, change_percent: 2.4 } }],
        }}
        onTickerSelect={onTickerSelect}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Filter by $SOL' }))
    expect(onTickerSelect).toHaveBeenCalledWith('SOL')
  })

  it('links financial price to the source website when available', () => {
    render(
      <TweetCard
        t={{
          ...baseTweet,
          assets: [
            {
              symbol: 'AAPL',
              kind: 'EQUITY',
              financials: {
                price: 185.12,
                change_percent: 1.73,
                website: 'https://finance.yahoo.com/quote/AAPL',
              },
            },
          ],
        }}
      />
    )

    const priceLink = screen.getByRole('link', { name: /^\$185[.,]12$/ })
    expect(priceLink).toHaveAttribute('href', 'https://finance.yahoo.com/quote/AAPL')
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
